"""All settings live here. Secrets come from environment variables only."""
import os

from dotenv import load_dotenv

from utils.tiny import tiny

load_dotenv()


def _str(name, default=""):
    return os.getenv(name, default).strip()


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _text(name, default):
    return os.getenv(name, default).replace("\\n", "\n")


# ---- Credentials ----
BOT_TOKEN = _str("BOT_TOKEN")
API_ID = _int("API_ID", 0)
API_HASH = _str("API_HASH")
MONGO_URI = _str("MONGO_URI")
MONGO_DB_NAME = _str("MONGO_DB_NAME", "tg_image_lab")
OWNER_ID = _int("OWNER_ID", 0)
LOG_CHANNEL_ID = _int("LOG_CHANNEL_ID", 0)
PORT = _int("PORT", 10000)  # Render web services must listen on $PORT

# ---- UI ----
UPDATE_CHANNEL_URL = _str("UPDATE_CHANNEL_URL", "https://t.me/telegram")
WELCOME_IMAGE = _str("WELCOME_IMAGE")
HELP_IMAGE = _str("HELP_IMAGE")
ABOUT_IMAGE = _str("ABOUT_IMAGE")

WELCOME_CAPTION = _text(
    "WELCOME_CAPTION",
    f"🎨 <b>{tiny('tg image lab')}</b>\n\n"
    f"{tiny('welcome')}, {{name}}!\n"
    f"{tiny('send me any image to open the editing dashboard.')}",
)
HELP_CAPTION = _text(
    "HELP_CAPTION",
    f"📖 <b>{tiny('help')}</b>\n\n"
    f"1️⃣ {tiny('send a jpeg, png or webp image')}\n"
    f"2️⃣ {tiny('pick crop, resize or brightness')}\n"
    f"3️⃣ {tiny('tap apply to preview each change')}\n"
    f"4️⃣ {tiny('use undo or reset anytime')}\n"
    f"5️⃣ {tiny('tap save to get your image')}",
)
ABOUT_CAPTION = _text(
    "ABOUT_CAPTION",
    f"ℹ️ <b>{tiny('about')}</b>\n\n"
    f"{tiny('tg image lab is a light, button-based image editor.')}\n"
    f"{tiny('built with python, aiogram 3 and pillow.')}",
)

# ---- Resource & session limits ----
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 10)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_IMAGE_PIXELS = _int("MAX_IMAGE_PIXELS", 16_000_000)
MAX_IMAGE_SIDE = _int("MAX_IMAGE_SIDE", 6000)
MIN_IMAGE_SIDE = 16
MAX_HISTORY_FRAMES = _int("MAX_HISTORY_FRAMES", 10)
SESSION_TIMEOUT_SEC = _int("SESSION_TIMEOUT_MIN", 15) * 60
MAX_CONCURRENT_JOBS = _int("MAX_CONCURRENT_JOBS", 2)
JOB_COOLDOWN_SEC = _int("JOB_COOLDOWN_SEC", 3)
PREVIEW_MAX_SIDE = _int("PREVIEW_MAX_SIDE", 1280)
TEMP_DIR = _str("TEMP_DIR", "temp_files")
