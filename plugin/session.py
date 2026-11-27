"""One editing session per user, with expiry, busy-flag and global job limits."""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import config
from plugin.list import EditHistory
from utils import temp_manager
from utils.tiny import tiny

log = logging.getLogger(__name__)

# At most N image jobs run at the same time across ALL users.
job_slots = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)


@dataclass
class EditSession:
    user_id: int
    chat_id: int
    session_id: str
    directory: str
    history: Optional[EditHistory] = None
    message_id: Optional[int] = None      # the dashboard message
    last_active: float = field(default_factory=time.monotonic)
    last_job: float = 0.0
    busy: bool = False                    # blocks conflicting operations
    awaiting: Optional[str] = None        # 'crop' | 'resize' | 'bright' while waiting for typed input
    pending: dict = field(default_factory=dict)

    def __post_init__(self):
        self.reset_pending()

    def reset_pending(self) -> None:
        self.awaiting = None
        self.pending = {
            "crop": {"ratio": None, "box": None, "pos": "c"},
            "resize": {"size": None, "keep": True},
            "bright": {"value": 0},
            "contrast": {"value": 0},
            "filter": {"key": None},
            "rot": {"op": None},
            # watermark settings survive resets (kept until the session ends)
            "wm": self.pending.get("wm") or {"text": None, "logo": False, "dir": None, "font": "default"},
        }

    def touch(self) -> None:
        self.last_active = time.monotonic()

    def is_expired(self) -> bool:
        return time.monotonic() - self.last_active > config.SESSION_TIMEOUT_SEC

    def cooldown_left(self) -> float:
        return max(0.0, config.JOB_COOLDOWN_SEC - (time.monotonic() - self.last_job))


class SessionManager:
    def __init__(self):
        self._sessions: dict = {}
        self._bot: Optional[Bot] = None
        self._task: Optional[asyncio.Task] = None

    def get(self, user_id: int) -> Optional[EditSession]:
        return self._sessions.get(user_id)

    def create(self, user_id: int, chat_id: int) -> EditSession:
        sid = uuid.uuid4().hex[:8]
        session = EditSession(user_id, chat_id, sid, temp_manager.create_session_dir(user_id, sid))
        self._sessions[user_id] = session
        return session

    async def close(self, user_id: int, *, delete_dashboard: bool = True, notice: str = None) -> None:
        """Remove ONLY this user's session, files and dashboard message."""
        s = self._sessions.pop(user_id, None)
        if not s:
            return
        temp_manager.remove_dir(s.directory)
        if not self._bot:
            return
        if delete_dashboard and s.message_id:
            try:
                await self._bot.delete_message(s.chat_id, s.message_id)
            except TelegramAPIError:
                pass
        if notice:
            try:
                await self._bot.send_message(s.chat_id, notice)
            except TelegramAPIError:
                pass

    # ---- background expiry ----
    def start(self, bot: Bot) -> None:
        self._bot = bot
        self._task = asyncio.create_task(self._expiry_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        self._sessions.clear()
        temp_manager.cleanup_all()

    async def _expiry_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                for s in list(self._sessions.values()):
                    if s.is_expired() and not s.busy:
                        await self.close(s.user_id, notice=f"⏰ {tiny('session expired. send a new image to start again.')}")
                active = {s.directory for s in self._sessions.values()}
                temp_manager.cleanup_abandoned(active, config.SESSION_TIMEOUT_SEC + 300)
            except Exception:
                log.exception("Expiry loop error")


sessions = SessionManager()
