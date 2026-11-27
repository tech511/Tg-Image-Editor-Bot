"""Keyboards and captions for the editing dashboard (all tiny-text, short callback data)."""
import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
from logic import crop, resize
from utils import image_utils
from utils.tiny import tiny

POSITIONS = {"s": ("↖️", "start"), "c": ("⏺", "center"), "e": ("↘️", "end")}


def _b(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def _kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def _mark(text, on):
    return f"✅ {text}" if on else text


def _back():
    return _b("🔙 " + tiny("back"), "nav:home")


def _apply(data):
    return _b("⚡ " + tiny("apply"), data)


def _custom(data):
    return _b("✏️ " + tiny("custom"), data)


# ---------- keyboards ----------
def main_kb():
    return _kb(
        [_b("✂️ " + tiny("crop"), "nav:crop"), _b("📐 " + tiny("resize"), "nav:resize")],
        [_b("☀️ " + tiny("brightness"), "nav:bright")],
        [_b("↩️ " + tiny("undo"), "ctl:undo"), _b("🔄 " + tiny("reset"), "ctl:reset")],
        [_b("💾 " + tiny("save"), "ctl:save"), _b("❌ " + tiny("close"), "ctl:close")],
    )


def crop_kb(p):
    ratios = [
        _b(_mark(label, p["box"] is None and p["ratio"] == v), f"cr:r:{v[0]}:{v[1]}")
        for label, v in crop.RATIOS.items()
    ]
    pos = [
        _b(_mark(f"{emoji} {tiny(name)}", p["pos"] == key), f"cr:p:{key}")
        for key, (emoji, name) in POSITIONS.items()
    ]
    return _kb(ratios[:3], ratios[3:] + [_custom("cr:custom")], pos, [_back(), _apply("cr:apply")])


def resize_kb(p):
    btns = [_b(_mark(f"{w}×{h}", p["size"] == (w, h)), f"rs:p:{w}x{h}") for w, h in resize.PRESETS]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    lock = "🔒" if p["keep"] else "🔓"
    state = tiny("on" if p["keep"] else "off")
    rows += [
        [_custom("rs:custom")],
        [_b(f"{lock} {tiny('keep aspect')}: {state}", "rs:ar")],
        [_back(), _apply("rs:apply")],
    ]
    return _kb(*rows)


def bright_kb(p):
    adj = [_b(label, f"br:a:{d}") for label, d in (("➖ 20", -20), ("➖ 10", -10), ("➕ 10", 10), ("➕ 20", 20))]
    return _kb(adj, [_custom("br:custom"), _b("♻️ " + tiny("reset"), "br:zero")], [_back(), _apply("br:apply")])


def panel_kb(s, panel):
    if panel == "crop":
        return crop_kb(s.pending["crop"])
    if panel == "resize":
        return resize_kb(s.pending["resize"])
    if panel == "bright":
        return bright_kb(s.pending["bright"])
    return main_kb()


# ---------- captions ----------
def warning(msg) -> str:
    return f"⚠️ {html.escape(str(msg))}"


def _head(s) -> str:
    w, h = image_utils.get_size(s.history.current_path)
    return (
        f"🖼 <b>{tiny('editing dashboard')}</b>\n"
        f"{tiny('size')}: <code>{w}×{h}</code>  •  "
        f"{tiny('edits')}: <code>{s.history.frame_count}/{config.MAX_HISTORY_FRAMES}</code>"
    )


def _crop_panel(s):
    p = s.pending["crop"]
    if p["box"]:
        x, y, w, h = p["box"]
        sel = f"<code>x={x} y={y} {w}×{h}</code>"
    elif p["ratio"]:
        sel = f"<code>{p['ratio'][0]}:{p['ratio'][1]}</code> • {tiny(POSITIONS[p['pos']][1])}"
    else:
        sel = "—"
    return (
        f"✂️ <b>{tiny('crop')}</b>",
        f"{tiny('selected')}: {sel}\n<i>{tiny('start = top/left, end = bottom/right')}</i>",
        f"{tiny('send')} <code>x y width height</code> {tiny('or a ratio like')} <code>5:4</code>",
    )


def _resize_panel(s):
    p = s.pending["resize"]
    if p["size"]:
        w, h = p["size"]
        sel = f"<code>{w or 'auto'}×{h or 'auto'}</code>"
    else:
        sel = "—"
    mode = tiny("fit inside, keep ratio") if p["keep"] else tiny("exact size")
    return (
        f"📐 <b>{tiny('resize')}</b>",
        f"{tiny('target')}: {sel}\n<i>{mode} • {tiny('no enlarging')}</i>",
        f"{tiny('send')} <code>800x600</code> {tiny('or only a width like')} <code>800</code>",
    )


def _bright_panel(s):
    v = s.pending["bright"]["value"]
    return (
        f"☀️ <b>{tiny('brightness')}</b>",
        f"{tiny('adjustment')}: <code>{v:+d}%</code>",
        f"{tiny('send a number from -100 to 100')}",
    )


_PANELS = {"crop": _crop_panel, "resize": _resize_panel, "bright": _bright_panel}


def dashboard_caption(s, note=None) -> str:
    text = f"{_head(s)}\n\n{tiny('choose a tool below.')}"
    return text + (f"\n\n{note}" if note else "")


def panel_caption(s, panel, note=None) -> str:
    if panel not in _PANELS:
        return dashboard_caption(s, note)
    title, summary, prompt = _PANELS[panel](s)
    text = f"{_head(s)}\n\n{title}\n{summary}"
    if s.awaiting == panel:
        text += f"\n\n✏️ {prompt}"
    return text + (f"\n\n{note}" if note else "")
