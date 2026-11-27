"""Resize engine. Never enlarges images. Pure Pillow, no Telegram code."""
import re

from PIL import Image

PRESETS = [(512, 512), (1080, 1080), (1280, 720), (1920, 1080), (720, 1280), (1080, 1920)]
MAX_DIM = 8000


def resize_image(img: Image.Image, width, height, keep_aspect: bool = True,
                 allow_upscale: bool = False) -> Image.Image:
    """Fit inside width x height (keep_aspect) or force exact size.
    width/height may be None (= unconstrained)."""
    w, h = img.size
    if keep_aspect:
        scales = []
        if width:
            scales.append(width / w)
        if height:
            scales.append(height / h)
        scale = min(scales)
        if not allow_upscale:
            scale = min(scale, 1.0)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    else:
        nw, nh = width or w, height or h
        if not allow_upscale:
            nw, nh = min(nw, w), min(nh, h)
    if (nw, nh) == (w, h):
        raise ValueError("No change: the image is already that size or smaller (enlarging is blocked).")
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def parse_custom(text: str):
    """'800x600' -> (800, 600); '800' -> (800, None); 'x600' -> (None, 600)."""
    nums = [int(n) for n in re.findall(r"\d+", text)]
    if re.match(r"^\s*[x×]\s*\d+\s*$", text, re.I) and len(nums) == 1:
        result = (None, nums[0])
    elif len(nums) == 1:
        result = (nums[0], None)
    elif len(nums) == 2:
        result = (nums[0], nums[1])
    else:
        raise ValueError("Send a size like 800x600, or just a width like 800.")
    if any(v is not None and not 1 <= v <= MAX_DIM for v in result):
        raise ValueError(f"Each side must be between 1 and {MAX_DIM}.")
    return result
