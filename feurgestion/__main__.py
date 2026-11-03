import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import Config, load_config
from .db import Database
from .handlers import events, info, moderation, welcome
from .middlewares import TrackerMiddleware

log = logging.getLogger("feurgestion")


async def on_startup(bot: Bot, cfg: Config) -> None:
    me = await bot.me()
    log.info("Connecté en tant que @%s — groupe %s — admins %s", me.username, cfg.chat_id, sorted(cfg.admin_ids))
    await events.check_bot_rights(bot, cfg)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    cfg = load_config()
    db = Database(cfg.db_path)
    await db.connect()

    bot = Bot(cfg.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    dp = Dispatcher(cfg=cfg, db=db)
    dp.message.outer_middleware(TrackerMiddleware(db, cfg))
    dp.include_routers(moderation.router, info.router, welcome.router, events.router)
    dp.startup.register(on_startup)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
