"""Brightness engine. Pure Pillow, no Telegram code."""
import re

from PIL import Image, ImageEnhance

MIN_VALUE, MAX_VALUE = -100, 100


def adjust_brightness(img: Image.Image, percent: int) -> Image.Image:
    """percent: -100 (black) .. +100 (twice as bright). Alpha is preserved."""
    percent = max(MIN_VALUE, min(MAX_VALUE, int(percent)))
    if percent == 0:
        raise ValueError("Adjustment is 0, nothing to apply.")
    factor = 1 + percent / 100
    if img.mode == "RGBA":
        r, g, b, a = img.split()
        out = ImageEnhance.Brightness(Image.merge("RGB", (r, g, b))).enhance(factor)
        out.putalpha(a)
        return out
    return ImageEnhance.Brightness(img).enhance(factor)


def parse_custom(text: str) -> int:
    m = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*%?\s*", text)
    if not m:
        raise ValueError("Send a number from -100 to 100.")
    value = round(float(m.group(1)))
    if not MIN_VALUE <= value <= MAX_VALUE:
        raise ValueError("The value must be between -100 and 100.")
    return value
