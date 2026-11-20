"""Sauvegardes de la base : chaque nuit en privé à l'admin, /backup à la demande, /restore pour revenir en arrière."""

import asyncio
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from ..config import Config
from ..db import Database
from ..filters import IsAdmin
from ..utils import PREFIXES

log = logging.getLogger(__name__)

router = Router(name="backup")

BACKUP_HOUR = 4  # sauvegarde automatique chaque nuit à 4 h (heure du groupe)
REQUIRED_TABLES = {"users", "actions", "settings"}


def _summary(stats: dict[str, int]) -> str:
    return f"👤 {stats['users']} · ⚖️ {stats['actions']} · ⚠️ {stats['warns']} · 🧪 {stats['flocko']} · 📜 {stats['quotes']}"


async def send_backup(bot: Bot, db: Database, cfg: Config, chat_id: int, silent: bool) -> None:
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "backup.db")
        await db.snapshot(path)
        data = await asyncio.to_thread(lambda: open(path, "rb").read())
    name = f"feurbot-{datetime.now(cfg.tz):%Y-%m-%d-%Hh%M}.db"
    caption = f"💾 {name}\n{_summary(await db.stats())}"
    await bot.send_document(chat_id, BufferedInputFile(data, name), caption=caption, disable_notification=silent)


async def backup_loop(bot: Bot, db: Database, cfg: Config) -> None:
    """Tourne en fond : une sauvegarde silencieuse chaque nuit dans la conversation privée de l'admin."""
    while True:
        now = datetime.now(cfg.tz)
        next_run = now.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            await send_backup(bot, db, cfg, cfg.log_chat_id or min(cfg.admin_ids), silent=True)
            log.info("Sauvegarde nocturne envoyée")
        except Exception:
            log.exception("Échec de la sauvegarde nocturne")


@router.message(Command("backup", "sauvegarde", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_backup(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    try:
        await send_backup(bot, db, cfg, message.from_user.id, silent=False)
    except TelegramAPIError:
        await message.reply("❌ Envoie-moi /start en privé d'abord.")
        return
    if message.chat.type != ChatType.PRIVATE:
        await message.reply("💾 Envoyée en privé")


def _is_backup(path: str) -> bool:
    """Vrai fichier SQLite du bot, et pas abîmé ?"""
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            healthy = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return False
    return healthy and REQUIRED_TABLES <= tables


@router.message(
    Command("restore", "restaurer", prefix=PREFIXES, ignore_case=True), IsAdmin(), F.chat.type == ChatType.PRIVATE
)
async def cmd_restore(message: Message, bot: Bot, db: Database) -> None:
    document = message.reply_to_message.document if message.reply_to_message else None
    if document is None or not (document.file_name or "").endswith(".db"):
        await message.reply("Usage : réponds à un fichier de sauvegarde avec <code>/restore</code>")
        return

    folder = os.path.dirname(db.path) or "."
    incoming = os.path.join(folder, "restauration.tmp")
    await bot.download(document, destination=incoming)
    if not await asyncio.to_thread(_is_backup, incoming):
        os.remove(incoming)
        await message.reply("❌ Ce n'est pas une sauvegarde valide.")
        return

    # Filet de sécurité : la base actuelle est gardée à côté avant d'être remplacée
    await db.snapshot(os.path.join(folder, "avant-restauration.db"))
    await db.replace_with(incoming)
    log.warning("Base restaurée depuis %s par %s", document.file_name, message.from_user.id)
    await message.reply(f"✅ Base restaurée\n{_summary(await db.stats())}")
