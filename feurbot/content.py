"""Contenus enregistrés (bienvenue, notes, filtres) : texte HTML + média éventuel."""

from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message, ReplyParameters, User
from aiogram.utils.text_decorations import html_decoration

from .config import Config
from .db import full_name
from .utils import mention

MEDIA_LABELS = {
    "photo": "📷 photo",
    "animation": "🎞 GIF",
    "video": "🎬 vidéo",
    "document": "📎 fichier",
    "audio": "🎵 audio",
    "voice": "🎙 vocal",
    "sticker": "🃏 sticker",
    "video_note": "⭕️ vidéo ronde",
}
CAPTIONLESS = ("sticker", "video_note")
PLACEHOLDERS = "{mention} {name} {username} {id} {chat} {count}"


def extract_media(message: Message | None) -> tuple[str | None, str | None]:
    if message is None:
        return None, None
    if message.photo:
        return "photo", message.photo[-1].file_id
    for kind in ("animation", "video", "sticker", "video_note", "voice", "audio", "document"):
        media = getattr(message, kind)
        if media:
            return kind, media.file_id
    return None, None


def html_args(message: Message, skip_words: int = 1) -> str:
    """Texte après la commande (et `skip_words - 1` mots de plus), en gardant la mise en forme
    (gras, liens, emojis premium...)."""
    text = message.text or message.caption or ""
    parts = text.split(maxsplit=skip_words)
    if len(parts) <= skip_words:
        return ""
    rest = parts[skip_words]
    start = len(text) - len(rest)
    # Telegram compte les positions des mises en forme en UTF-16
    cut = len(text[:start].encode("utf-16-le")) // 2
    entities = []
    for entity in message.entities or message.caption_entities or []:
        end = entity.offset + entity.length
        if end <= cut:
            continue
        begin = max(entity.offset, cut)
        entities.append(entity.model_copy(update={"offset": begin - cut, "length": end - begin}))
    return html_decoration.unparse(rest, entities).strip()


async def render(template: str, user: User, bot: Bot, cfg: Config) -> str:
    name = full_name(user.first_name, user.last_name)
    values = {
        "{mention}": mention(user.id, name),
        "{name}": escape(name),
        "{username}": f"@{escape(user.username)}" if user.username else escape(name),
        "{id}": str(user.id),
    }
    if "{chat}" in template:
        values["{chat}"] = escape((await bot.get_chat(cfg.chat_id)).title or "")
    if "{count}" in template:
        values["{count}"] = str(await bot.get_chat_member_count(cfg.chat_id))
    for key, value in values.items():
        template = template.replace(key, value)
    return template


async def send_content(
    bot: Bot,
    chat_id: int,
    text: str | None,
    media_type: str | None = None,
    file_id: str | None = None,
    reply_to: int | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    if not media_type:
        await bot.send_message(chat_id, text or "…", reply_parameters=reply, reply_markup=reply_markup)
        return

    send = getattr(bot, f"send_{media_type}")
    if media_type in CAPTIONLESS:
        await send(chat_id, file_id, reply_parameters=reply)
        if text:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return
    try:
        await send(chat_id, file_id, caption=text, reply_parameters=reply, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "too long" not in exc.message:
            raise
        # Légende limitée à 1024 caractères : média puis texte à part
        await send(chat_id, file_id, reply_parameters=reply)
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
