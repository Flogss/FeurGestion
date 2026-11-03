"""Tous les messages qui ne sont pas des commandes : #notes, filtres, @admin et « quoi → feur »."""

import re

from aiogram import Bot, Router
from aiogram.types import Message

from ..config import Config
from ..db import Database
from ..filters import InManagedChat
from ..jokes import feur_reply
from ..utils import on_cooldown
from .notes import find_filter, send_snippet
from .tools import report

router = Router(name="passive")

NOTE_TAG = re.compile(r"^#([\w-]{1,32})\b")
ADMIN_CALL = re.compile(r"(?<!\w)@admins?\b", re.I)


@router.message(InManagedChat())
async def on_message(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    if not message.from_user or message.from_user.is_bot or message.sender_chat:
        return
    text = message.text or message.caption
    if not text:
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

    answer = feur_reply(text)
    if answer and await db.get_setting("feur", True) and not on_cooldown(f"feur:{message.chat.id}", 10):
        await message.reply(answer)
