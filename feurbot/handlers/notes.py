"""Notes (#nom), filtres (réponses automatiques à un mot) et règles du groupe."""

import re
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..content import PLACEHOLDERS, extract_media, html_args, render, send_content
from ..db import Database
from ..filters import IsAdmin, IsMember
from ..utils import PREFIXES

router = Router(name="notes")

NOTE_NAME = re.compile(r"[\w-]{1,32}")
RULES = ("rules", "regles")  # kind et nom de la ligne qui stocke les règles


def _parse_name(args: str) -> tuple[str | None, int]:
    """Nom en tête des arguments, entre guillemets s'il fait plusieurs mots.

    Retourne (nom, nombre de mots à sauter pour trouver le contenu, commande comprise).
    """
    args = args.strip()
    if not args:
        return None, 0
    quoted = re.match(r'^["«“]\s*(.+?)\s*["»”]', args)
    if quoted:
        raw = args[: quoted.end()]
        return quoted.group(1).lower(), 1 + len(raw.split())
    return args.split()[0].lower(), 2


def _content(message: Message, skip_words: int) -> tuple[str | None, str | None, str | None]:
    """Texte (HTML) et média à enregistrer : dans la commande elle-même ou dans le message visé."""
    text = html_args(message, skip_words) or None
    media_type, file_id = extract_media(message)
    reply = message.reply_to_message
    if reply:
        if not media_type:
            media_type, file_id = extract_media(reply)
        if not text and (reply.text or reply.caption):
            text = reply.html_text
    return text, media_type, file_id


async def send_snippet(message: Message, row, bot: Bot, cfg: Config) -> None:
    text = await render(row["text"], message.from_user, bot, cfg) if row["text"] else None
    reply_to = message.reply_to_message.message_id if message.reply_to_message else message.message_id
    await send_content(bot, message.chat.id, text, row["media_type"], row["file_id"], reply_to=reply_to)


async def find_filter(db: Database, text: str):
    for row in await db.list_snippets("filter"):
        if re.search(rf"(?<!\w){re.escape(row['name'])}(?!\w)", text, re.IGNORECASE):
            return row
    return None


# --- Notes ---


@router.message(Command("save", "note", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_save(message: Message, command: CommandObject, db: Database) -> None:
    name, skip = _parse_name(command.args or "")
    if not name or not NOTE_NAME.fullmatch(name):
        await message.reply(
            "Usage : <code>.save nom texte</code>, ou <code>.save nom</code> en réponse à un message / média.\n"
            "Nom : lettres, chiffres, <code>_</code> et <code>-</code>. Pas d'espace, on n'est pas des sauvages.\n"
            f"Variables : <code>{PLACEHOLDERS}</code>"
        )
        return
    text, media_type, file_id = _content(message, skip)
    if not text and not media_type:
        await message.reply("❌ Une note vide ? Même mes blagues ont plus de contenu.")
        return
    await db.save_snippet("note", name, text, media_type, file_id, message.from_user.id)
    await message.reply(f"📝 Note <code>#{escape(name)}</code> enregistrée. Tape <code>#{escape(name)}</code> pour la ressortir.")


@router.message(Command("get", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_get(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    name, _ = _parse_name(command.args or "")
    row = await db.get_snippet("note", name.lstrip("#")) if name else None
    if row is None:
        await message.reply("❌ Note introuvable. Regarde la liste avec <code>.notes</code>.")
        return
    await send_snippet(message, row, bot, cfg)


@router.message(Command("notes", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_notes(message: Message, db: Database) -> None:
    rows = await db.list_snippets("note")
    if not rows:
        await message.reply("📭 Aucune note. Le vide intersidéral.")
        return
    names = " ".join(f"<code>#{escape(row['name'])}</code>" for row in rows)
    await message.reply(f"<b>📒 Notes ({len(rows)})</b>\n{names}\n\nTape le #nom pour en afficher une.")


@router.message(Command("clear", "delnote", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_clear(message: Message, command: CommandObject, db: Database) -> None:
    name, _ = _parse_name(command.args or "")
    if name and await db.delete_snippet("note", name.lstrip("#")):
        await message.reply(f"🗑 Note <code>#{escape(name.lstrip('#'))}</code> supprimée. Paix à son âme.")
    else:
        await message.reply("❌ Note introuvable. Difficile de supprimer ce qui n'existe pas.")


# --- Filtres ---


@router.message(Command("filter", "filtre", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_filter(message: Message, command: CommandObject, db: Database) -> None:
    trigger, skip = _parse_name(command.args or "")
    text, media_type, file_id = _content(message, skip) if trigger else (None, None, None)
    if not trigger or (not text and not media_type):
        await message.reply(
            "Usage : <code>.filter mot réponse</code> ou <code>.filter \"plusieurs mots\" réponse</code>, "
            "ou en réponse à un message / média.\nQuand quelqu'un écrit le mot, je réponds. Comme pour « quoi ». 😏"
        )
        return
    await db.save_snippet("filter", trigger, text, media_type, file_id, message.from_user.id)
    await message.reply(f"✅ Filtre « {escape(trigger)} » enregistré. Je guette.")


@router.message(Command("filters", "filtres", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_filters(message: Message, db: Database) -> None:
    rows = await db.list_snippets("filter")
    if not rows:
        await message.reply("📭 Aucun filtre. À part « quoi → feur », mais celui-là est gravé dans le marbre.")
        return
    names = "\n".join(f"• <code>{escape(row['name'])}</code>" for row in rows)
    await message.reply(f"<b>🎯 Filtres ({len(rows)})</b>\n{names}")


@router.message(Command("stop", "delfilter", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_stop(message: Message, command: CommandObject, db: Database) -> None:
    trigger, _ = _parse_name(command.args or "")
    if trigger and await db.delete_snippet("filter", trigger):
        await message.reply(f"🗑 Filtre « {escape(trigger)} » supprimé. Je ne guette plus.")
    else:
        await message.reply("❌ Filtre introuvable. Liste : <code>.filters</code>")


# --- Règles ---


@router.message(Command("setrules", "setregles", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_setrules(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    text, media_type, file_id = _content(message, 1)
    if not text and not media_type:
        await message.reply("Usage : <code>.setrules texte des règles</code> (ou en réponse à un message).")
        return
    try:
        await send_content(bot, message.chat.id, text, media_type, file_id)
    except TelegramBadRequest as exc:
        await message.reply(f"❌ Telegram n'en veut pas : {escape(exc.message)}")
        return
    await db.save_snippet(*RULES, text, media_type, file_id, message.from_user.id)
    await message.reply("✅ Règles enregistrées ☝️ Maintenant plus personne ne pourra dire qu'il savait pas.")


@router.message(Command("rules", "regles", "règles", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_rules(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    row = await db.get_snippet(*RULES)
    if row is None:
        await message.reply("📜 Pas de règles. C'est l'anarchie. Enfin presque : PUB = MUTE.")
        return
    await send_snippet(message, row, bot, cfg)
