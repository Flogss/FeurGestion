"""Tous les messages qui ne sont pas des commandes : mot interdit, #notes, filtres, @admin et « quoi → feur »."""

import logging
import random
import re

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, ReactionTypeEmoji

from ..config import Config
from ..db import Database
from ..filters import InManagedChat
from ..jokes import EASTER_EGGS, FEUR_TITLES, analyze
from ..targets import Target
from ..utils import on_cooldown
from .games import check_forbidden_word
from .notes import find_filter, send_snippet
from .tools import report

log = logging.getLogger(__name__)

router = Router(name="passive")

NOTE_TAG = re.compile(r"^#([\w-]{1,32})\b")
ADMIN_CALL = re.compile(r"(?<!\w)@admins?\b", re.I)
EASTER_EGG_CHANCE = 1 / 500


@router.message(InManagedChat())
async def on_message(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    if not message.from_user or message.from_user.is_bot or message.sender_chat:
        return
    text = message.text or message.caption
    if not text:
        return

    if await check_forbidden_word(message, bot, db, cfg):
        return

    tag = NOTE_TAG.match(text)
    if tag:
        row = await db.get_snippet("note", tag.group(1))
        if row:
            await send_snippet(message, row, bot, cfg)
            return

    if ADMIN_CALL.search(text) and message.reply_to_message:
        await report(message, bot, cfg)
        return

    row = await find_filter(db, text)
    if row:
        await send_snippet(message, row, bot, cfg)
        return

    if await _feur(message, text, db):
        return

    if random.random() < EASTER_EGG_CHANCE:
        await message.reply(random.choice(EASTER_EGGS))


async def _feur(message: Message, text: str, db: Database) -> bool:
    """Réactions, réplique « feur » et titres du feurboard. Retourne True si le bot a répondu."""
    result = analyze(text)
    enabled = await db.get_setting("feur", True)

    count = await db.add_feur(message.from_user.id) if result.is_quoi else 0
    if not enabled:
        return False

    if result.reaction:
        try:
            await message.react([ReactionTypeEmoji(emoji=result.reaction)])
        except TelegramAPIError as exc:
            log.debug("Réaction impossible : %s", exc)

    if count in FEUR_TITLES:
        await message.reply(
            f"🏅 {Target.from_user(message.from_user).mention} : {FEUR_TITLES[count]} ({count} « quoi »)"
        )
        return True
    if result.answer and not on_cooldown(f"feur:{message.chat.id}", 10):
        await message.reply(result.answer)
        return True
    return False
