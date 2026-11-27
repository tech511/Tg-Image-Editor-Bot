"""Reusable image helpers: validation, open/save, previews. No Telegram code here."""
import io
import os

from PIL import Image, ImageOps, UnidentifiedImageError

import config

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

# Pillow raises an error above 2x this value (decompression-bomb guard).
Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS * 2


class ImageError(Exception):
    """Raised with a user-friendly message."""


def validate_image(path: str) -> str:
    """Check size, format, resolution and corruption. Returns the format name."""
    if os.path.getsize(path) > config.MAX_UPLOAD_BYTES:
        raise ImageError(f"The file is larger than {config.MAX_UPLOAD_MB} MB.")
    try:
        with Image.open(path) as img:
            fmt, (w, h) = img.format, img.size
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ImageError("This file is not a valid or readable image.") from None
    if fmt not in ALLOWED_FORMATS:
        raise ImageError("Only JPEG, PNG and WEBP images are supported.")
    if w * h > config.MAX_IMAGE_PIXELS or max(w, h) > config.MAX_IMAGE_SIDE:
        raise ImageError(
            f"The image is too large ({w}×{h}). Max {config.MAX_IMAGE_SIDE}px per side "
            f"and {config.MAX_IMAGE_PIXELS // 1_000_000} megapixels."
        )
    if min(w, h) < config.MIN_IMAGE_SIDE:
        raise ImageError("The image is too small.")
    return fmt


def open_image(path: str) -> Image.Image:
    """Open fully loaded, EXIF-rotated, and in RGB/RGBA mode."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        keep_alpha = img.mode in ("LA", "PA") or "transparency" in img.info
        img = img.convert("RGBA" if keep_alpha else "RGB")
    return img


def has_alpha(img: Image.Image) -> bool:
    return img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 255


def flatten(img: Image.Image) -> Image.Image:
    """Return an RGB image (transparent areas become white)."""
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    return img if img.mode == "RGB" else img.convert("RGB")


def frame_extension(img: Image.Image) -> str:
    return ".png" if has_alpha(img) else ".jpg"


def save_image(img: Image.Image, path: str) -> None:
    """PNG for .png, otherwise JPEG (quality 92)."""
    if os.path.splitext(path)[1].lower() == ".png":
        img.save(path, "PNG", compress_level=3)
    else:
        flatten(img).save(path, "JPEG", quality=92)


def prepare_original(raw_path: str, directory: str) -> str:
    """Validate the download, normalise it, and store it as the session's original."""
    fmt = validate_image(raw_path)
    img = open_image(raw_path)
    try:
        ext = ".png" if fmt == "PNG" or has_alpha(img) else ".jpg"
        dest = os.path.join(directory, "original" + ext)
        save_image(img, dest)
    finally:
        img.close()
    os.remove(raw_path)
    return dest


def get_size(path: str) -> tuple:
    with Image.open(path) as img:  # reads the header only
        return img.size


def make_preview(path: str) -> bytes:
    """Small JPEG for the dashboard message (keeps Telegram uploads light)."""
    m = config.PREVIEW_MAX_SIDE
    with Image.open(path) as img:
        img.draft("RGB", (m, m))
        img.thumbnail((m, m), Image.Resampling.LANCZOS)
        rgb = flatten(img)
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=85)
        return buf.getvalue()
