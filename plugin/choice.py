"""Main editing controller: uploads, dashboard, tool panels, history controls, save/close."""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Filter
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, InputMediaPhoto, Message

import config
from logic import brightness, crop, resize
from plugin import ui
from plugin.list import EditHistory
from plugin.session import EditSession, job_slots, sessions
from utils import image_utils
from utils.tiny import tiny

log = logging.getLogger(__name__)
router = Router(name="choice")
router.message.filter(F.chat.type == "private")


# ======================= helpers =======================
@asynccontextmanager
async def _busy(s: EditSession):
    s.busy = True
    try:
        yield
    finally:
        s.busy = False


async def _get_session(cb: CallbackQuery):
    """Return the caller's session if this button belongs to their live dashboard."""
    s = sessions.get(cb.from_user.id)
    if s is None or s.history is None or cb.message is None or cb.message.message_id != s.message_id:
        await cb.answer(tiny("session expired. send a new image."), show_alert=True)
        return None
    if s.busy:
        await cb.answer(tiny("processing..."))
        return None
    s.touch()
    return s


async def _edit_caption(bot, s, caption, kb):
    """Never raises: a failed cosmetic edit must not break the session."""
    try:
        await bot.edit_message_caption(chat_id=s.chat_id, message_id=s.message_id,
                                       caption=caption, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            log.warning("Caption edit failed: %s", e)
    except TelegramAPIError as e:
        log.warning("Caption edit failed: %s", e)


async def _refresh_media(bot, s, note=None):
    """Show the current frame on the main dashboard."""
    data = await asyncio.to_thread(image_utils.make_preview, s.history.current_path)
    try:
        await bot.edit_message_media(
            media=InputMediaPhoto(media=BufferedInputFile(data, "preview.jpg"),
                                  caption=ui.dashboard_caption(s, note)),
            chat_id=s.chat_id, message_id=s.message_id, reply_markup=ui.main_kb(),
        )
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            raise


def _apply_job(s: EditSession, op):
    """Runs in a worker thread: open current frame -> edit -> save new frame."""
    with image_utils.open_image(s.history.current_path) as img:
        result = op(img)
    try:
        s.history.push(result)
    finally:
        result.close()


async def _run_edit(cb: CallbackQuery, s: EditSession, panel: str, op):
    left = s.cooldown_left()
    if left > 0:
        await cb.answer(f"{tiny('please wait')} {left:.0f}s", show_alert=True)
        return
    bot = cb.bot
    async with _busy(s):
        await cb.answer()
        await _edit_caption(bot, s, f"⏳ <b>{tiny('processing...')}</b>", None)
        try:
            async with job_slots:
                await asyncio.to_thread(_apply_job, s, op)
            s.last_job = time.monotonic()
            s.reset_pending()
            try:
                await _refresh_media(bot, s, note=f"✅ {tiny('editing completed!')}")
            except TelegramAPIError:
                s.history.undo()  # Telegram refused the preview, so drop the frame
                raise
        except ValueError as e:
            await _edit_caption(bot, s, ui.panel_caption(s, panel, ui.warning(e)), ui.panel_kb(s, panel))
        except TelegramAPIError as e:
            log.warning("Preview rejected: %s", e)
            await _edit_caption(bot, s, ui.panel_caption(s, "home", ui.warning("Telegram rejected the result (unusual dimensions).")), ui.main_kb())
        except Exception:
            log.exception("Edit failed")
            await _edit_caption(bot, s, ui.panel_caption(s, "home", ui.warning("Something went wrong. Please try again.")), ui.main_kb())


# ======================= upload =======================
@router.message(F.photo)
async def on_photo(message: Message):
    p = message.photo[-1]
    await _start_session(message, p.file_id, p.file_size)


@router.message(F.document.mime_type.in_(image_utils.ALLOWED_MIME))
async def on_document(message: Message):
    d = message.document
    await _start_session(message, d.file_id, d.file_size)


@router.message(F.document.mime_type.startswith("image/"))
async def on_bad_document(message: Message):
    await message.answer(f"⚠️ {tiny('only jpeg, png and webp are supported.')}")


async def _start_session(message: Message, file_id: str, file_size):
    user_id = message.from_user.id
    if sessions.get(user_id):
        await message.answer(f"⚠️ {tiny('you already have an active edit. save or close it first.')}")
        return
    if file_size and file_size > config.MAX_UPLOAD_BYTES:
        await message.answer(f"⚠️ {tiny('image is too big.')} {tiny('max')} {config.MAX_UPLOAD_MB} MB.")
        return

    s = sessions.create(user_id, message.chat.id)  # no await since the check above: one session per user
    status = await message.answer(f"⏳ <b>{tiny('processing...')}</b>")
    try:
        raw = os.path.join(s.directory, "upload.bin")
        await message.bot.download(file_id, destination=raw)
        async with job_slots:
            original = await asyncio.to_thread(image_utils.prepare_original, raw, s.directory)
        s.history = EditHistory(s.directory, original)
        data = await asyncio.to_thread(image_utils.make_preview, original)
        sent = await message.bot.send_photo(
            s.chat_id, BufferedInputFile(data, "preview.jpg"),
            caption=ui.dashboard_caption(s), reply_markup=ui.main_kb(),
        )
        s.message_id = sent.message_id
        s.touch()
        await status.delete()
    except image_utils.ImageError as e:
        await sessions.close(user_id)
        await status.edit_text(ui.warning(e))
    except Exception:
        log.exception("Upload failed")
        await sessions.close(user_id)
        try:
            await status.edit_text(ui.warning("Could not open this image. Please try another one."))
        except TelegramAPIError:
            pass


# ======================= navigation =======================
@router.callback_query(F.data.startswith("nav:"))
async def on_nav(cb: CallbackQuery):
    s = await _get_session(cb)
    if not s:
        return
    panel = cb.data.split(":", 1)[1]
    s.awaiting = None
    if panel == "home":
        s.reset_pending()
    await cb.answer()
    await _edit_caption(cb.bot, s, ui.panel_caption(s, panel), ui.panel_kb(s, panel))


async def _show(cb, s, panel):
    await cb.answer()
    await _edit_caption(cb.bot, s, ui.panel_caption(s, panel), ui.panel_kb(s, panel))


# ======================= crop / resize / brightness =======================
@router.callback_query(F.data.startswith("cr:"))
async def on_crop(cb: CallbackQuery):
    s = await _get_session(cb)
    if not s:
        return
    _, action, *args = cb.data.split(":")
    p = s.pending["crop"]
    if action == "apply":
        if p["box"]:
            x, y, w, h = p["box"]
            op = lambda img: crop.crop_box(img, x, y, w, h)
        elif p["ratio"]:
            rw, rh = p["ratio"]
            pos = p["pos"]
            op = lambda img: crop.crop_ratio(img, rw, rh, pos)
        else:
            await cb.answer(tiny("select a ratio first"), show_alert=True)
            return
        await _run_edit(cb, s, "crop", op)
        return
    if action == "r":
        p["ratio"], p["box"], s.awaiting = (int(args[0]), int(args[1])), None, None
    elif action == "p":
        p["pos"] = args[0]
    elif action == "custom":
        s.awaiting = "crop"
    await _show(cb, s, "crop")


@router.callback_query(F.data.startswith("rs:"))
async def on_resize(cb: CallbackQuery):
    s = await _get_session(cb)
    if not s:
        return
    _, action, *args = cb.data.split(":")
    p = s.pending["resize"]
    if action == "apply":
        if not p["size"]:
            await cb.answer(tiny("select a size first"), show_alert=True)
            return
        w, h = p["size"]
        keep = p["keep"]
        await _run_edit(cb, s, "resize", lambda img: resize.resize_image(img, w, h, keep_aspect=keep))
        return
    if action == "p":
        w, h = args[0].split("x")
        p["size"], s.awaiting = (int(w), int(h)), None
    elif action == "ar":
        p["keep"] = not p["keep"]
    elif action == "custom":
        s.awaiting = "resize"
    await _show(cb, s, "resize")


@router.callback_query(F.data.startswith("br:"))
async def on_bright(cb: CallbackQuery):
    s = await _get_session(cb)
    if not s:
        return
    _, action, *args = cb.data.split(":")
    p = s.pending["bright"]
    if action == "apply":
        v = p["value"]
        if v == 0:
            await cb.answer(tiny("adjust the value first"), show_alert=True)
            return
        await _run_edit(cb, s, "bright", lambda img: brightness.adjust_brightness(img, v))
        return
    if action == "a":
        p["value"] = max(brightness.MIN_VALUE, min(brightness.MAX_VALUE, p["value"] + int(args[0])))
        s.awaiting = None
    elif action == "zero":
        p["value"], s.awaiting = 0, None
    elif action == "custom":
        s.awaiting = "bright"
    await _show(cb, s, "bright")


# ======================= typed custom input =======================
class Awaiting(Filter):
    async def __call__(self, message: Message) -> bool:
        s = sessions.get(message.from_user.id)
        return bool(s and s.awaiting and message.text and not message.text.startswith("/"))


@router.message(F.text, Awaiting())
async def on_custom_input(message: Message):
    s = sessions.get(message.from_user.id)
    text = message.text
    try:
        await message.delete()  # keep the chat clean
    except TelegramAPIError:
        pass
    if s.busy or s.history is None:
        return
    s.touch()
    panel = s.awaiting
    note = None
    try:
        w, h = image_utils.get_size(s.history.current_path)
        if panel == "crop":
            mode, val = crop.parse_custom(text)
            if mode == "ratio":
                s.pending["crop"].update(ratio=val, box=None)
            else:
                crop.check_box(w, h, *val)
                s.pending["crop"].update(box=val)
        elif panel == "resize":
            s.pending["resize"]["size"] = resize.parse_custom(text)
        elif panel == "bright":
            s.pending["bright"]["value"] = brightness.parse_custom(text)
        s.awaiting = None
    except ValueError as e:
        note = ui.warning(e)  # stay in input mode so the user can retry
    await _edit_caption(message.bot, s, ui.panel_caption(s, panel, note), ui.panel_kb(s, panel))


# ======================= undo / reset / save / close =======================
@router.callback_query(F.data.startswith("ctl:"))
async def on_control(cb: CallbackQuery):
    s = await _get_session(cb)
    if not s:
        return
    action = cb.data.split(":", 1)[1]

    if action == "close":
        await cb.answer()
        await sessions.close(s.user_id)
        return
    if action == "save":
        await _save(cb, s)
        return

    if not s.history.can_undo:
        await cb.answer(tiny("nothing to undo" if action == "undo" else "nothing to reset"), show_alert=True)
        return
    async with _busy(s):
        await cb.answer()
        if action == "undo":
            s.history.undo()
            note = f"↩️ {tiny('undo done')}"
        else:
            s.history.reset()
            note = f"🔄 {tiny('restored original')}"
        s.reset_pending()
        try:
            await _refresh_media(cb.bot, s, note=note)
        except TelegramAPIError as e:
            log.warning("Refresh failed: %s", e)


async def _save(cb: CallbackQuery, s: EditSession):
    async with _busy(s):
        await cb.answer(tiny("saving..."))
        path = s.history.current_path
        name = "tg_image_lab" + os.path.splitext(path)[1]
        try:
            await cb.bot.send_document(
                s.chat_id, FSInputFile(path, filename=name),
                caption=f"✅ <b>{tiny('editing completed!')}</b>",
            )
        except TelegramAPIError as e:
            log.warning("Save failed: %s", e)
            await cb.answer(tiny("could not send the file. try again."), show_alert=True)
            return
    await sessions.close(s.user_id)
