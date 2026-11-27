"""/start command and the Help / About / Close navigation."""
import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton as Btn, InlineKeyboardMarkup, Message

import config
from database import user_info
from utils.tiny import tiny

log = logging.getLogger(__name__)
router = Router(name="start")
router.message.filter(F.chat.type == "private")


def _start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="📖 " + tiny("help"), callback_data="st:help"),
         Btn(text="ℹ️ " + tiny("about"), callback_data="st:about")],
        # Middle row. Intentionally NOT connected to any action yet.
        [Btn(text="⚙️ " + tiny("setting"), callback_data="st:setting")],
        [Btn(text="📢 " + tiny("update channel"), url=config.UPDATE_CHANNEL_URL),
         Btn(text="❌ " + tiny("close"), callback_data="st:close")],
    ])


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        Btn(text="🔙 " + tiny("back"), callback_data="st:home"),
        Btn(text="❌ " + tiny("close"), callback_data="st:close"),
    ]])


def _welcome(user) -> str:
    return config.WELCOME_CAPTION.replace("{name}", html.escape(user.first_name or "friend"))


async def _send_page(bot: Bot, chat_id: int, image: str, caption: str, kb) -> None:
    """Photo page when an image is configured; falls back to plain text on any error."""
    if image:
        try:
            await bot.send_photo(chat_id, image, caption=caption, reply_markup=kb)
            return
        except TelegramAPIError as e:
            log.warning("Page image failed (%s), sending text instead.", e)
    await bot.send_message(chat_id, caption, reply_markup=kb)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    try:
        await user_info.track_user(bot, message.from_user)
    except Exception:
        log.exception("User tracking failed")  # never block /start
    await _send_page(bot, message.chat.id, config.WELCOME_IMAGE, _welcome(message.from_user), _start_kb())


@router.callback_query(F.data.in_({"st:help", "st:about", "st:home"}))
async def on_page(cb: CallbackQuery, bot: Bot):
    if cb.data == "st:help":
        image, caption, kb = config.HELP_IMAGE, config.HELP_CAPTION, _back_kb()
    elif cb.data == "st:about":
        image, caption, kb = config.ABOUT_IMAGE, config.ABOUT_CAPTION, _back_kb()
    else:
        image, caption, kb = config.WELCOME_IMAGE, _welcome(cb.from_user), _start_kb()
    await cb.answer()
    chat_id = cb.message.chat.id
    try:  # delete the old message and send a fresh one (no editing)
        await cb.message.delete()
    except TelegramAPIError:
        pass
    await _send_page(bot, chat_id, image, caption, kb)


@router.callback_query(F.data == "st:close")
async def on_close(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.delete()
    except TelegramAPIError:
        pass
