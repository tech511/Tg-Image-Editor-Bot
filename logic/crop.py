"""Crop engine. Pure Pillow, no Telegram code. Raises ValueError with readable messages."""
import re

from PIL import Image

RATIOS = {"1:1": (1, 1), "4:3": (4, 3), "16:9": (16, 9), "3:4": (3, 4), "9:16": (9, 16)}
_POS = {"s": 0.0, "c": 0.5, "e": 1.0}  # start / center / end of the free axis


def check_box(img_w: int, img_h: int, x: int, y: int, w: int, h: int) -> None:
    if w < 1 or h < 1 or x < 0 or y < 0:
        raise ValueError("Values must be positive (x and y can be 0).")
    if x + w > img_w or y + h > img_h:
        raise ValueError(f"The crop area must fit inside {img_w}×{img_h}.")
    if (w, h) == (img_w, img_h):
        raise ValueError("That crop covers the whole image.")


def crop_box(img: Image.Image, x: int, y: int, w: int, h: int) -> Image.Image:
    """Crop by coordinates: top-left (x, y) plus width/height in pixels."""
    check_box(img.width, img.height, x, y, w, h)
    return img.crop((x, y, x + w, y + h))


def crop_ratio(img: Image.Image, rw: int, rh: int, position: str = "c") -> Image.Image:
    """Largest crop with ratio rw:rh. position: s=top/left, c=center, e=bottom/right."""
    w, h = img.size
    if w * rh > h * rw:  # image is wider than the ratio
        cw, ch = h * rw // rh, h
    else:
        cw, ch = w, w * rh // rw
    cw, ch = max(1, cw), max(1, ch)
    f = _POS.get(position, 0.5)
    return crop_box(img, round((w - cw) * f), round((h - ch) * f), cw, ch)


def parse_custom(text: str):
    """'5:4' -> ('ratio', (5, 4)); 'x y w h' -> ('box', (x, y, w, h))."""
    nums = [int(n) for n in re.findall(r"\d+", text)]
    if ":" in text and len(nums) == 2:
        if min(nums) < 1:
            raise ValueError("Ratio values must be at least 1.")
        return "ratio", (nums[0], nums[1])
    if len(nums) == 4:
        return "box", tuple(nums)
    raise ValueError("Send a ratio like 5:4 or four numbers: x y width height.")
