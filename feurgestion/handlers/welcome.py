from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, User

from ..config import Config
from ..db import Database, full_name
from ..filters import IsAdmin
from ..utils import PREFIXES, mention

router = Router(name="welcome")

DEFAULT_WELCOME = {
    "enabled": True,
    "text": "👋 Bienvenue {mention} sur <b>{chat}</b> !",
    "media_type": None,
    "media_id": None,
}
MEDIA_LABELS = {"photo": "📷 photo", "animation": "🎞 GIF", "video": "🎬 vidéo"}


async def get_welcome(db: Database) -> dict:
    return {**DEFAULT_WELCOME, **await db.get_setting("welcome", {})}


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


async def send_welcome(bot: Bot, chat_id: int, conf: dict, text: str) -> None:
    media_type, media_id = conf["media_type"], conf["media_id"]
    if not media_type:
        await bot.send_message(chat_id, text)
        return
    send = {"photo": bot.send_photo, "animation": bot.send_animation, "video": bot.send_video}[media_type]
    try:
        await send(chat_id, media_id, caption=text)
    except TelegramBadRequest as exc:
        if "too long" not in exc.message:
            raise
        # Légende limitée à 1024 caractères : média puis texte à part
        await send(chat_id, media_id)
        await bot.send_message(chat_id, text)


async def greet(user: User, bot: Bot, db: Database, cfg: Config) -> None:
    conf = await get_welcome(db)
    if conf["enabled"]:
        await send_welcome(bot, cfg.chat_id, conf, await render(conf["text"], user, bot, cfg))


def _media(message: Message) -> tuple[str | None, str | None]:
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.animation:
        return "animation", message.animation.file_id
    if message.video:
        return "video", message.video.file_id
    return None, None


def _html_args(message: Message) -> str:
    """Texte après la commande, en gardant la mise en forme (gras, liens, emojis premium...)."""
    parts = message.html_text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


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
        await message.reply("✅ Bienvenue activée." if conf["enabled"] else "⛔️ Bienvenue désactivée.")
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

    media_type, media_id = _media(message)
    if not media_type and message.reply_to_message:
        media_type, media_id = _media(message.reply_to_message)
    new_text = _html_args(message)

    if not media_type and not new_text:
        state = "✅ activée" if conf["enabled"] else "⛔️ désactivée"
        await message.reply(
            f"<b>👋 Message de bienvenue</b> — {state}\n"
            f"Média : {MEDIA_LABELS.get(conf['media_type'], 'aucun')}\n"
            "Aperçu avec toi comme nouveau membre ⬇️"
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
        if not new_text or "parse entities" not in exc.message:
            await message.reply(f"❌ Telegram a refusé : {escape(exc.message)}")
            return
        # Mise en forme illisible pour Telegram : on garde le texte brut
        updated["text"] = escape((command.args or "").strip())
        await _preview(message, updated, bot, cfg)

    await db.set_setting("welcome", updated)
    await message.reply("✅ Message de bienvenue enregistré, voilà l'aperçu ☝️")
