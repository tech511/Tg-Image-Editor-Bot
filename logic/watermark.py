"""Watermark engine (text or logo). Pure Pillow, no Telegram code.
Size is chosen automatically from the image size."""
import os
import re
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from utils import image_utils

# direction code -> readable name (row letter t/m/b + column letter l/c/r)
DIRECTIONS = {
    "tl": "top left", "tc": "top center", "tr": "top right",
    "ml": "middle left", "mc": "center", "mr": "middle right",
    "bl": "bottom left", "bc": "bottom center", "br": "bottom right",
}
MAX_TEXT = 40
LOGO_STORE_SIDE = 600     # stored logo is shrunk to this (saves disk/RAM)
WIDTH_RATIO = 0.25        # watermark width  <= 25% of image width
HEIGHT_RATIO = 0.15       # watermark height <= 15% of image height
MARGIN_RATIO = 0.03       # gap from the edges
LOGO_OPACITY = 0.92
BG_TOLERANCE = 38         # max colour distance still treated as "background"

# ---------------------------------------------------------------- fonts
# Put your own .ttf/.otf files in the folder below and they become buttons too.
FONTS_DIR = os.getenv("FONTS_DIR", "fonts")
_BUILTIN = {  # key -> (label, candidate file names; first one that loads wins)
    "default": ("default", ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf"]),
    "serif": ("serif", ["DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf", "timesbd.ttf"]),
    "mono": ("mono", ["DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf", "courbd.ttf"]),
    "italic": ("italic", ["DejaVuSans-BoldOblique.ttf", "LiberationSans-BoldItalic.ttf", "arialbi.ttf"]),
    "light": ("light", ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf"]),
    "narrow": ("narrow", ["DejaVuSansCondensed-Bold.ttf", "LiberationSansNarrow-Bold.ttf"]),
}


@lru_cache(maxsize=1)
def _scan():
    """Find usable fonts once. Returns ({key: path}, ((key, label), ...))."""
    paths, labels = {}, [("default", "default")]
    for key, (label, names) in _BUILTIN.items():
        for name in names:
            try:
                ImageFont.truetype(name, 20)
            except OSError:
                continue
            paths[key] = name
            if key != "default":
                labels.append((key, label))
            break
    if os.path.isdir(FONTS_DIR):
        files = sorted(f for f in os.listdir(FONTS_DIR) if f.lower().endswith((".ttf", ".otf")))[:8]
        for i, f in enumerate(files):
            path = os.path.join(FONTS_DIR, f)
            try:
                ImageFont.truetype(path, 20)
            except OSError:
                continue
            paths[f"u{i}"] = path
            labels.append((f"u{i}", os.path.splitext(f)[0][:14]))
    return paths, tuple(labels)


def list_fonts() -> list:
    """[(key, label), ...] - 'default' is always first and always works."""
    return list(_scan()[1])


def _font(key: str, size: int):
    paths = _scan()[0]
    path = paths.get(key) or paths.get("default")
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)  # Pillow >= 10.1


# ---------------------------------------------------------------- helpers
def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        raise ValueError("The watermark text is empty.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"Keep the text under {MAX_TEXT} characters.")
    return text


def _place(img: Image.Image, layer: Image.Image, direction: str) -> Image.Image:
    if direction not in DIRECTIONS:
        raise ValueError("Choose a direction first.")
    w, h = img.size
    lw, lh = layer.size
    m = max(2, int(min(w, h) * MARGIN_RATIO))
    x = {"l": m, "c": (w - lw) // 2, "r": w - lw - m}[direction[1]]
    y = {"t": m, "m": (h - lh) // 2, "b": h - lh - m}[direction[0]]
    base = img.convert("RGBA")
    base.alpha_composite(layer, dest=(max(0, x), max(0, y)))
    return base if img.mode == "RGBA" else base.convert("RGB")


# ---------------------------------------------------------------- logo
def _border_points(w: int, h: int):
    pts = [(x, 0) for x in range(0, w, 2)] + [(x, h - 1) for x in range(0, w, 2)]
    return pts + [(0, y) for y in range(0, h, 2)] + [(w - 1, y) for y in range(0, h, 2)]


def _remove_background(logo: Image.Image):
    """Remove a plain background (white, black, any single colour) touching the edges.
    Returns (RGBA image, True if the logo now has a transparent background)."""
    alpha = logo.getchannel("A")
    if alpha.getextrema()[0] < 200:
        return logo, True  # already transparent
    rgb = logo.convert("RGB")
    w, h = rgb.size
    pts = _border_points(w, h)
    border = [rgb.getpixel(p) for p in pts]
    bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    close = sum(1 for c in border if max(abs(c[i] - bg[i]) for i in range(3)) <= BG_TOLERANCE)
    if close / len(border) < 0.7:
        return logo, False  # background is not a plain colour

    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg))
    r, g, b = diff.split()
    dist = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mask = dist.point(lambda v: 255 if v <= BG_TOLERANCE else 0)  # 255 = looks like background
    for p in pts:  # fill only background connected to the edges, so inner details stay
        if mask.getpixel(p) == 255:
            ImageDraw.floodfill(mask, p, 128)
    keep = mask.point(lambda v: 0 if v == 128 else 255)
    keep = keep.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))  # clean soft edge
    if keep.getbbox() is None or sum(keep.histogram()[128:]) < w * h * 0.02:
        return logo, False  # would erase the whole logo
    out = logo.copy()
    out.putalpha(keep)
    return out, True


def prepare_logo(raw_path: str, dest_png: str) -> bool:
    """Validate an uploaded logo, strip its background, trim it and store a small PNG.
    Returns True when the logo has a transparent background."""
    image_utils.validate_image(raw_path)  # raises ImageError
    img = image_utils.open_image(raw_path)
    try:
        logo = img.convert("RGBA")
    finally:
        img.close()
    logo.thumbnail((LOGO_STORE_SIDE, LOGO_STORE_SIDE), Image.Resampling.LANCZOS)
    logo, removed = _remove_background(logo)
    bbox = logo.getchannel("A").getbbox()
    if bbox:
        logo = logo.crop(bbox)
    logo.save(dest_png, "PNG")
    logo.close()
    return removed


def apply_logo(img: Image.Image, logo_path: str, direction: str) -> Image.Image:
    """Logo only (no background) with a soft drop shadow for a premium look."""
    w, h = img.size
    with Image.open(logo_path) as src:
        logo = src.convert("RGBA")
    scale = min(w * WIDTH_RATIO / logo.width, h * HEIGHT_RATIO / logo.height)
    size = (max(1, int(logo.width * scale)), max(1, int(logo.height * scale)))
    small = logo.resize(size, Image.Resampling.LANCZOS)
    logo.close()

    alpha = small.getchannel("A")
    small.putalpha(alpha.point(lambda v: int(v * LOGO_OPACITY)))
    pad = max(3, size[1] // 8)
    off = max(1, size[1] // 30)
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda v: int(v * 0.38)))
    layer = Image.new("RGBA", (size[0] + 2 * pad, size[1] + 2 * pad), (0, 0, 0, 0))
    layer.alpha_composite(shadow, (pad + off, pad + off))
    layer = layer.filter(ImageFilter.GaussianBlur(max(1, size[1] / 28)))
    layer.alpha_composite(small, (pad, pad))
    shadow.close()
    small.close()
    try:
        return _place(img, layer, direction)
    finally:
        layer.close()


# ---------------------------------------------------------------- text
def apply_text(img: Image.Image, text: str, direction: str, font_key: str = "default") -> Image.Image:
    """White text with a soft shadow, sized automatically."""
    text = clean_text(text)
    w, h = img.size
    l, t, r, b = _font(font_key, 100).getbbox(text)
    scale = min(w * WIDTH_RATIO / max(1, r - l), h * HEIGHT_RATIO / max(1, b - t))
    size = max(10, int(100 * scale))
    font = _font(font_key, size)
    l, t, r, b = font.getbbox(text)
    pad = max(4, size // 3)
    off = max(1, size // 18)

    shadow = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((pad - l + off, pad - t + off), text, font=font, fill=(0, 0, 0, 175))
    layer = shadow.filter(ImageFilter.GaussianBlur(max(1, size / 16)))
    shadow.close()
    ImageDraw.Draw(layer, "RGBA").text((pad - l, pad - t), text, font=font, fill=(255, 255, 255, 240))
    try:
        return _place(img, layer, direction)
    finally:
        layer.close()
