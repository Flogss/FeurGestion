import asyncio
import logging

import orjson
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from . import deezer
from .app import build_dispatcher
from .commands import sync_commands
from .config import Config, load_config
from .db import Database
from .handlers import backup, events, memory

log = logging.getLogger("feurbot")


_background: set[asyncio.Task] = set()


async def on_startup(bot: Bot, cfg: Config, db: Database) -> None:
    me = await bot.me()
    log.info("Connecté en tant que @%s — groupe %s — admins %s", me.username, cfg.chat_id, sorted(cfg.admin_ids))
    stats = await db.stats()
    log.info("Base %s : %s", db.path, ", ".join(f"{count} {table}" for table, count in stats.items()))
    await events.check_bot_rights(bot, cfg)
    await sync_commands(bot, cfg, db)
    for loop in (memory.birthday_loop(bot, db, cfg), backup.backup_loop(bot, db, cfg)):
        task = asyncio.create_task(loop)
        _background.add(task)
        task.add_done_callback(_background.discard)


async def on_shutdown() -> None:
    for task in _background:
        task.cancel()
    await deezer.close()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    cfg = load_config()
    db = Database(cfg.db_path, cfg.tz)
    await db.connect()

    # orjson : lecture et écriture JSON bien plus rapides pour chaque échange avec Telegram
    session = AiohttpSession(json_loads=orjson.loads, json_dumps=lambda value: orjson.dumps(value).decode())
    bot = Bot(
        cfg.token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = build_dispatcher(cfg, db)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        import uvloop  # boucle d'événements plus rapide (Linux / macOS)
    except ImportError:
        asyncio.run(main())
    else:
        uvloop.run(main())
