"""MongoDB 'user_info' collection: register new users, keep stored info fresh."""
import html
import logging
from datetime import datetime, timezone

from aiogram.exceptions import TelegramAPIError
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

import config

log = logging.getLogger(__name__)
_client = None
_col = None


async def init() -> None:
    global _client, _col
    if not config.MONGO_URI:
        log.warning("MONGO_URI not set: user tracking is disabled.")
        return
    _client = AsyncMongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
    _col = _client[config.MONGO_DB_NAME]["user_info"]
    await _col.create_index("user_id", unique=True)
    log.info("MongoDB connected.")


async def close() -> None:
    if _client is not None:
        await _client.close()


async def _current_info(bot, user) -> dict:
    bio = None
    try:
        bio = (await bot.get_chat(user.id)).bio
    except TelegramAPIError:
        pass
    return {
        "user_id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "language_code": user.language_code,
        "is_premium": bool(user.is_premium),
        "bio": bio,
    }


async def track_user(bot, user) -> None:
    """Call on /start. Inserts new users (and logs them), updates only changed fields."""
    if _col is None:
        return
    info = await _current_info(bot, user)
    now = datetime.now(timezone.utc)
    stored = await _col.find_one({"user_id": user.id})

    if stored is None:
        doc = {**info, "registered_at": now}
        try:
            await _col.insert_one(doc)
        except DuplicateKeyError:
            return  # another request registered them first
        await _log_new_user(bot, doc)
        return

    changes = {k: v for k, v in info.items() if stored.get(k) != v}
    if changes:  # skip the write when nothing changed
        await _col.update_one({"user_id": user.id}, {"$set": {**changes, "updated_at": now}})


async def _log_new_user(bot, doc: dict) -> None:
    if not config.LOG_CHANNEL_ID:
        return
    e = html.escape
    name = e(" ".join(filter(None, [doc["first_name"], doc["last_name"]])))
    text = (
        "🆕 <b>New user</b>\n\n"
        f"<b>ID:</b> <code>{doc['user_id']}</code>\n"
        f"<b>Name:</b> {name}\n"
        f"<b>Username:</b> {('@' + e(doc['username'])) if doc['username'] else '—'}\n"
        f"<b>Language:</b> {e(doc['language_code'] or '—')}\n"
        f"<b>Premium:</b> {'yes' if doc['is_premium'] else 'no'}\n"
        f"<b>Bio:</b> {e(doc['bio'] or '—')}\n"
        f"<b>Registered:</b> {doc['registered_at']:%Y-%m-%d %H:%M} UTC"
    )
    try:
        await bot.send_message(config.LOG_CHANNEL_ID, text)
    except TelegramAPIError as err:
        log.warning("Could not post to log channel: %s", err)
