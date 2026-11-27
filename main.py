"""TG Image Lab entry point."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

import config
from database import user_info
from handler import start
from plugin import choice
from plugin.session import sessions
from utils import temp_manager

log = logging.getLogger("tg-image-lab")


async def _start_health_server() -> web.AppRunner:
    """Render web services need an open port. Also handy for uptime pings."""
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="TG Image Lab is running"))
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    return runner


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing. Set it in .env or your Render environment.")

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(choice.router)  # uploads + editing
    dp.include_router(start.router)   # /start + help/about

    temp_manager.cleanup_all()
    await user_info.init()
    sessions.start(bot)
    runner = await _start_health_server()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Bot started.")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await sessions.stop()
        await user_info.close()
        await runner.cleanup()
        await bot.session.close()
        log.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
