"""/ia question — et répondre à un message de l'IA continue la conversation."""

import logging
import re
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from .. import ai
from ..config import Config
from ..db import Database
from ..filters import IsMember
from ..utils import PREFIXES, on_cooldown

log = logging.getLogger(__name__)

router = Router(name="ia")

COOLDOWN = 8  # secondes entre deux questions d'une même personne
MAX_TURNS = 10  # messages gardés en mémoire par conversation
_threads: dict[int, list[dict]] = {}  # id du message de l'IA -> historique de la conversation


def _format(text: str) -> str:
    """Le modèle écrit en Markdown : on garde juste le gras et l'italique, le reste en texte brut."""
    text = escape(text[:3500])
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
    return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)


async def _answer(message: Message, history: list[dict], bot: Bot) -> None:
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        answer = await ai.ask(history, message.from_user.first_name)
    except ai.AIError:
        await message.reply("🤖💤 L'IA fait la sieste, réessaie dans un instant.")
        return
    sent = await message.reply(_format(answer))
    if len(_threads) > 500:
        _threads.clear()
    _threads[sent.message_id] = [*history, {"role": "assistant", "content": answer}][-MAX_TURNS:]


def is_ai_reply(message: Message, bot: Bot) -> bool:
    reply = message.reply_to_message
    return bool(reply and reply.from_user and reply.from_user.id == bot.id and reply.message_id in _threads)


async def continue_thread(message: Message, bot: Bot, db: Database) -> None:
    """Quelqu'un répond à un message de l'IA : on poursuit la même conversation."""
    if not await db.get_setting("ia", True) or on_cooldown(f"ia:{message.from_user.id}", COOLDOWN):
        return
    text = message.text or message.caption or ""
    history = [*_threads[message.reply_to_message.message_id], {"role": "user", "content": text}]
    await _answer(message, history[-MAX_TURNS:], bot)


@router.message(Command("ia", "ai", "ask", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_ia(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    question = (command.args or "").strip()
    if question.lower() in ("on", "off") and message.from_user.id in cfg.admin_ids:
        await db.set_setting("ia", question.lower() == "on")
        await message.reply("🤖 IA activée" if question.lower() == "on" else "🤖 IA désactivée")
        return
    if not ai.enabled() or not await db.get_setting("ia", True):
        await message.reply("🤖 IA désactivée.")
        return

    reply = message.reply_to_message
    quoted = (reply.text or reply.caption) if reply and reply.from_user and reply.from_user.id != bot.id else None
    if not question and not quoted:
        await message.reply("Usage : <code>/ia ta question</code>")
        return
    if on_cooldown(f"ia:{message.from_user.id}", COOLDOWN):
        return
    if quoted:
        author = reply.from_user.first_name
        question = f"Message de {author} : « {quoted[:1500]} »\n\n{question or 'Réagis à ce message.'}"
    await _answer(message, [{"role": "user", "content": question}], bot)
