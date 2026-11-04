"""Verrous : droits Telegram du groupe (médias, stickers...) et suppression auto (liens, transferts)."""

import logging
import re
from html import escape

from aiogram import Bot, Router
from aiogram.enums import MessageEntityType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions, Message

from ..config import Config
from ..db import Database
from ..filters import IsAdmin
from ..targets import Target
from ..utils import PREFIXES, delete_later, group_admin_ids

log = logging.getLogger(__name__)

router = Router(name="locks")

SEND_FIELDS = [
    "can_send_messages", "can_send_audios", "can_send_documents", "can_send_photos", "can_send_videos",
    "can_send_video_notes", "can_send_voice_notes", "can_send_polls", "can_send_other_messages",
    "can_add_web_page_previews",
]
# Verrous gérés par les droits Telegram : nom -> (droits concernés, description)
PERMISSION_LOCKS = {
    "tout": (SEND_FIELDS, "💬 tout (groupe en lecture seule)"),
    "medias": (
        ["can_send_photos", "can_send_videos", "can_send_audios", "can_send_documents",
         "can_send_voice_notes", "can_send_video_notes"],
        "🖼 photos, vidéos, vocaux, fichiers",
    ),
    "stickers": (["can_send_other_messages"], "🃏 stickers, GIFs et jeux"),
    "sondages": (["can_send_polls"], "📊 sondages"),
    "apercus": (["can_add_web_page_previews"], "🪟 aperçus de liens"),
}
# Verrous gérés par le bot : il supprime les messages des non-admins
DELETE_LOCKS = {
    "liens": "🔗 liens et pubs (supprimés)",
    "transferts": "📨 messages transférés (supprimés)",
}
ALIASES = {
    "all": "tout", "lien": "liens", "links": "liens", "pub": "liens", "pubs": "liens", "url": "liens",
    "media": "medias", "médias": "medias", "média": "medias", "sticker": "stickers", "gif": "stickers",
    "gifs": "stickers", "sondage": "sondages", "polls": "sondages", "aperçus": "apercus", "apercu": "apercus",
    "transfert": "transferts", "forward": "transferts", "forwards": "transferts",
}
LINK_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.(me|dog)/|\b[\w-]+\.(com|fr|net|org|io|gg|xyz|link|ly)\b)", re.I)
NOTICES = {
    "liens": "🔗 Pas de liens ici, {mention}. PUB = MUTE, c'est écrit dans la bio. Ceci était ton avertissement amical 🙂",
    "transferts": "📨 Les transferts sont interdits ici, {mention}. Écris avec tes propres mots, tu sais faire.",
}


def _usage() -> str:
    names = ", ".join(f"<code>{name}</code>" for name in (*PERMISSION_LOCKS, *DELETE_LOCKS))
    return f"Usage : <code>.lock type</code> / <code>.unlock type</code>\nTypes : {names}"


async def _set_permission_lock(name: str, locked: bool, bot: Bot, cfg: Config) -> None:
    chat = await bot.get_chat(cfg.chat_id)
    current = (chat.permissions or ChatPermissions()).model_dump()
    for field in PERMISSION_LOCKS[name][0]:
        current[field] = not locked
    await bot.set_chat_permissions(cfg.chat_id, ChatPermissions(**current), use_independent_chat_permissions=True)


async def _toggle(message: Message, command: CommandObject, locked: bool, bot: Bot, db: Database, cfg: Config) -> None:
    raw = (command.args or "").strip().lower()
    name = ALIASES.get(raw, raw)
    if name not in PERMISSION_LOCKS and name not in DELETE_LOCKS:
        await message.reply(_usage())
        return

    if name in PERMISSION_LOCKS:
        try:
            await _set_permission_lock(name, locked, bot, cfg)
        except TelegramAPIError as exc:
            await message.reply(f"❌ Telegram a refusé : {escape(exc.message)}")
            return
        label = PERMISSION_LOCKS[name][1]
    else:
        active = set(await db.get_setting("locks", []))
        if locked:
            active.add(name)
        else:
            active.discard(name)
        await db.set_setting("locks", sorted(active))
        label = DELETE_LOCKS[name]

    if locked:
        await message.reply(
            f"🔒 Verrouillé : {label}.\n<i>Les admins et les modos, eux, font ce qu'ils veulent. Privilège.</i>"
        )
    else:
        await message.reply(f"🔓 Déverrouillé : {label}.\n<i>Soyez sages. Ou au moins discrets.</i>")


@router.message(Command("lock", "verrou", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_lock(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    await _toggle(message, command, True, bot, db, cfg)


@router.message(Command("unlock", "deverrou", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_unlock(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    await _toggle(message, command, False, bot, db, cfg)


@router.message(Command("locks", "verrous", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_locks(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    perms = (await bot.get_chat(cfg.chat_id)).permissions or ChatPermissions()
    active = set(await db.get_setting("locks", []))
    lines = ["<b>🔐 Verrous</b>"]
    for name, (fields, label) in PERMISSION_LOCKS.items():
        locked = all(getattr(perms, field) is False for field in fields)
        lines.append(f"{'🔒' if locked else '🔓'} <code>{name}</code> — {label}")
    for name, label in DELETE_LOCKS.items():
        lines.append(f"{'🔒' if name in active else '🔓'} <code>{name}</code> — {label}")
    await message.reply("\n".join(lines))


def has_link(message: Message) -> bool:
    for entity in message.entities or message.caption_entities or []:
        if entity.type in (MessageEntityType.URL, MessageEntityType.TEXT_LINK):
            return True
    return bool(LINK_RE.search(message.text or message.caption or ""))


async def enforce(message: Message, bot: Bot, db: Database, cfg: Config) -> bool:
    """Supprime le message s'il enfreint un verrou. Retourne True s'il a été supprimé."""
    active = await db.get_setting("locks", [])
    if not active or message.from_user.is_bot:
        return False
    violation = None
    if "transferts" in active and message.forward_origin:
        violation = "transferts"
    elif "liens" in active and has_link(message):
        violation = "liens"
    if violation is None or message.from_user.id in await group_admin_ids(bot, cfg):
        return False
    if await db.is_mod(message.from_user.id):
        return False

    try:
        await message.delete()
    except TelegramAPIError as exc:
        log.warning("Suppression impossible (%s) : %s", violation, exc)
        return False
    log.info("Message de %s supprimé (verrou %s)", message.from_user.id, violation)
    notice = await bot.send_message(
        message.chat.id, NOTICES[violation].format(mention=Target.from_user(message.from_user).mention)
    )
    delete_later(bot, notice.chat.id, notice.message_id, 20)
    return True
