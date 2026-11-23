"""Résumé drôle de la journée, écrit par l'IA chaque soir (et /resume pour le lancer à la main)."""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .. import ai
from ..config import Config
from ..db import Database
from ..filters import IsAdmin
from ..utils import PREFIXES

log = logging.getLogger(__name__)

router = Router(name="resume")

SUMMARY_HOUR = 23  # chaque soir à 23 h (heure du groupe)
MIN_MESSAGES = 10  # en dessous, pas de résumé : il ne s'est rien passé
CHUNK_CHARS = 14000  # au-delà, on résume par morceaux puis on assemble

SYSTEM = (
    "Tu es FeurBot, le chroniqueur officiel du groupe Telegram « feurchat ». On te donne les messages "
    "échangés depuis le dernier résumé (heure, pseudo, message). Écris un résumé DRÔLE en français, au second "
    "degré, façon chroniqueur de JT qui chambre gentiment (parle d'« aujourd'hui », c'est le soir même) : "
    "les grands sujets, les moments marquants, les "
    "embrouilles, les meilleures phrases (cite les pseudos), qui a le plus parlé, et termine par "
    "« 🏆 Le moment du jour » et « 🤡 Le prix du jour ». Glisse une blague « quoi ? feur » si ça s'y prête. "
    "10 à 20 lignes, emojis bienvenus, pas de titres Markdown ni de tableaux. Pas de méchanceté gratuite, "
    "rien d'humiliant sur le physique, et ne recopie pas d'informations personnelles (adresses, numéros)."
)
NOTES = (
    "Résume ce morceau de conversation en notes factuelles et courtes (qui, quoi, phrases marquantes avec "
    "pseudos), pour un résumé final écrit plus tard. 15 lignes maximum."
)


def _format(text: str) -> str:
    text = escape(text[:3800])
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)


def _transcript(rows, cfg: Config) -> str:
    return "\n".join(
        f"{datetime.fromtimestamp(row['at'], cfg.tz):%H:%M} {row['name']}: {row['text']}" for row in rows
    )


def _chunks(text: str) -> list[str]:
    chunks, current = [], ""
    for line in text.split("\n"):
        if current and len(current) + len(line) > CHUNK_CHARS:
            chunks.append(current)
            current = ""
        current += line + "\n"
    return [*chunks, current] if current else chunks


async def make_summary(db: Database, cfg: Config) -> tuple[str, int] | None:
    """(résumé, dernier id résumé) ou None s'il n'y a pas assez de messages."""
    rows = await db.chat_lines()
    if len(rows) < MIN_MESSAGES:
        return None
    pieces = _chunks(_transcript(rows, cfg))
    if len(pieces) > 1:
        notes = []
        for index, piece in enumerate(pieces):
            if index:
                await asyncio.sleep(10)  # on ménage le quota Groq
            notes.append(await ai.complete(
                [{"role": "system", "content": NOTES}, {"role": "user", "content": piece}], 600
            ))
        material = "Notes prises au fil de la journée :\n\n" + "\n\n".join(notes)
    else:
        material = pieces[0]
    summary = await ai.complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": material}], 1500)
    return summary, rows[-1]["id"]


async def post_summary(bot: Bot, db: Database, cfg: Config, chat_id: int | None = None) -> bool:
    result = await make_summary(db, cfg)
    if result is None:
        return False
    summary, last_id = result
    await bot.send_message(chat_id or cfg.chat_id, f"📰 <b>Le résumé du jour</b>\n\n{_format(summary)}")
    await db.forget_chat_lines(last_id)
    log.info("Résumé publié (messages jusqu'à #%s)", last_id)
    return True


async def summary_loop(bot: Bot, db: Database, cfg: Config) -> None:
    """Tourne en fond : chaque soir, le résumé de tout ce qui s'est dit depuis le précédent."""
    while True:
        now = datetime.now(cfg.tz)
        next_run = now.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        if not ai.enabled() or not await db.get_setting("resume", True):
            continue
        try:
            await post_summary(bot, db, cfg)
        except (ai.AIError, TelegramAPIError):
            log.exception("Résumé du soir impossible")


@router.message(Command("resume", "résumé", "recap", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_resume(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    arg = (command.args or "").strip().lower()
    if arg in ("on", "off"):
        await db.set_setting("resume", arg == "on")
        await message.reply("📰 Résumé du soir activé" if arg == "on" else "📰 Résumé du soir désactivé")
        return
    if not ai.enabled():
        await message.reply("🤖 IA désactivée.")
        return
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        posted = await post_summary(bot, db, cfg)
    except ai.AIError:
        await message.reply("🤖💤 L'IA fait la sieste, réessaie dans un instant.")
        return
    if not posted:
        await message.reply("📰 Rien à résumer depuis le dernier résumé.")
    elif message.chat.id != cfg.chat_id:
        await message.reply("📰 Publié dans le groupe")
