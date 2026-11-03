from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, User

from ..config import Config
from ..content import MEDIA_LABELS, extract_media, html_args, render, send_content
from ..db import Database
from ..filters import IsAdmin
from ..utils import PREFIXES

router = Router(name="welcome")

DEFAULT_WELCOME = {
    "enabled": True,
    "text": (
        "👋 Bienvenue {mention} sur <b>{chat}</b> !\n"
        "Règle n°1 : ici on ne dit pas « quoi ». Tu sais très bien pourquoi. 😏"
    ),
    "media_type": None,
    "media_id": None,
}


async def get_welcome(db: Database) -> dict:
    return {**DEFAULT_WELCOME, **await db.get_setting("welcome", {})}


async def send_welcome(bot: Bot, chat_id: int, conf: dict, text: str) -> None:
    await send_content(bot, chat_id, text, conf["media_type"], conf["media_id"])


async def greet(user: User, bot: Bot, db: Database, cfg: Config) -> None:
    conf = await get_welcome(db)
    if conf["enabled"]:
        await send_welcome(bot, cfg.chat_id, conf, await render(conf["text"], user, bot, cfg))


async def _preview(message: Message, conf: dict, bot: Bot, cfg: Config) -> None:
    text = await render(conf["text"], message.from_user, bot, cfg)
    await send_welcome(bot, message.chat.id, conf, text)


@router.message(Command("welcome", "bienvenue", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_welcome(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    conf = await get_welcome(db)
    keyword = (command.args or "").strip().lower()

    if keyword in ("on", "off"):
        conf["enabled"] = keyword == "on"
        await db.set_setting("welcome", conf)
        await message.reply(
            "✅ Bienvenue activée. Les nouveaux seront accueillis comme des rois (ou presque)."
            if conf["enabled"]
            else "⛔️ Bienvenue désactivée. Les nouveaux entreront dans un silence gênant."
        )
        return
    if keyword in ("reset", "nomedia"):
        if keyword == "reset":
            conf = dict(DEFAULT_WELCOME)
        else:
            conf["media_type"] = conf["media_id"] = None
        await db.set_setting("welcome", conf)
        await _preview(message, conf, bot, cfg)
        await message.reply("✅ C'est fait, voilà l'aperçu ☝️")
        return

    media_type, media_id = extract_media(message)
    if not media_type:
        media_type, media_id = extract_media(message.reply_to_message)
    new_text = html_args(message)

    if not media_type and not new_text:
        state = "✅ activée" if conf["enabled"] else "⛔️ désactivée"
        await message.reply(
            f"<b>👋 Message de bienvenue</b> — {state}\n"
            f"Média : {MEDIA_LABELS.get(conf['media_type'], 'aucun')}\n"
            "Aperçu avec toi dans le rôle du petit nouveau ⬇️"
        )
        await _preview(message, conf, bot, cfg)
        return

    updated = dict(conf)
    if media_type:
        updated["media_type"], updated["media_id"] = media_type, media_id
    if new_text:
        updated["text"] = new_text

    try:
        await _preview(message, updated, bot, cfg)
    except TelegramBadRequest as exc:
        await message.reply(f"❌ Telegram n'en veut pas : {escape(exc.message)}")
        return

    await db.set_setting("welcome", updated)
    await message.reply("✅ Enregistré ! Aperçu ☝️ (oui, c'est toi le nouveau pour l'occasion)")
