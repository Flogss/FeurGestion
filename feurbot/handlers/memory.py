"""La mémoire du groupe : feurboard, livre d'or des citations, top des bavards, anniversaires."""

import asyncio
import logging
from datetime import date, datetime, timedelta
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database, full_name
from ..filters import IsMember, IsStaff
from ..jokes import MONTHS, TOP_TITLES, feur_title
from ..targets import reply_error, resolve_target
from ..utils import PREFIXES, mention, on_cooldown

log = logging.getLogger(__name__)

router = Router(name="memory")


def _who(row) -> str:
    name = full_name(row["first_name"], row["last_name"]) if row["first_name"] else str(row["user_id"])
    return mention(row["user_id"], name)


# --- Feurboard ---


@router.message(Command("feurboard", "topfeur", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_feurboard(message: Message, db: Database) -> None:
    rows = await db.feur_board(10)
    if not rows:
        await message.reply("🏆 Personne n'a encore dit « quoi ».")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = ["<b>🏆 Feurboard</b>"]
    for rank, row in enumerate(rows):
        badge = medals[rank] if rank < 3 else f"{rank + 1}."
        lines.append(f"{badge} {_who(row)} — {row['count']} · {feur_title(row['count'])}")
    await message.reply("\n".join(lines))


# --- Livre d'or ---


def _format_quote(row) -> str:
    said = datetime.fromtimestamp(row["said_at"])
    return (
        f"📜 « {escape(row['text'])} »\n"
        f"— {mention(row['user_id'], row['author_name'])}, {MONTHS[said.month - 1]} {said.year} "
        f"<i>(#{row['id']})</i>"
    )


@router.message(Command("citer", "quote", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_citer(message: Message, bot: Bot, db: Database) -> None:
    reply = message.reply_to_message
    if message.chat.type == ChatType.PRIVATE or reply is None or not reply.from_user:
        await message.reply("📜 Réponds au message à citer.")
        return
    text = reply.text or reply.caption
    if not text:
        await message.reply("📜 Pas de texte à citer.")
        return
    if reply.from_user.id == bot.id:
        await message.reply("📜 Pas moi.")
        return
    if on_cooldown(f"citer:{message.from_user.id}", 10):
        return
    author = full_name(reply.from_user.first_name, reply.from_user.last_name)
    quote_id = await db.add_quote(
        reply.from_user.id, author, text[:1000], int(reply.date.timestamp()), reply.message_id, message.from_user.id
    )
    if quote_id is None:
        await message.reply("📜 Déjà cité.")
        return
    await message.reply(f"📜 Citation <b>#{quote_id}</b> enregistrée")


@router.message(Command("citation", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_citation(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    arg = (command.args or "").strip().lstrip("#")
    if arg.isdigit() and len(arg) < 5:
        row = await db.get_quote(int(arg))
        if row is None:
            await message.reply(f"📜 Pas de citation #{arg}.")
            return
    else:
        target, _, error = await resolve_target(message, command.args or "", bot, db, cfg) if arg else (None, "", None)
        if error:
            await reply_error(message, error)
            return
        row = await db.random_quote(target.id if target else None)
        if row is None:
            await message.reply(f"📜 Aucune citation{' de ' + target.mention if target else ''}.")
            return
    await message.reply(_format_quote(row))


@router.message(Command("delcitation", "uncite", prefix=PREFIXES, ignore_case=True), IsStaff())
async def cmd_delcitation(message: Message, command: CommandObject, db: Database) -> None:
    arg = (command.args or "").strip().lstrip("#")
    if arg.isdigit() and await db.delete_quote(int(arg)):
        await message.reply(f"🗑 Citation #{arg} supprimée")
    else:
        await message.reply("Usage : <code>/delcitation 12</code>")


# --- Top des bavards ---


@router.message(Command("top", "bavards", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_top(message: Message, db: Database) -> None:
    rows = await db.top_talkers(days=7, limit=10)
    if not rows:
        await message.reply("📊 Personne n'a parlé cette semaine.")
        return
    lines = ["<b>📊 Top de la semaine</b>"]
    for rank, row in enumerate(rows):
        lines.append(f"{TOP_TITLES[rank]} : {_who(row)} — {row['total']} messages")
    ghost = await db.ghost(days=7)
    if ghost and ghost["user_id"] not in {row["user_id"] for row in rows}:
        lines.append(f"👻 Fantôme : {_who(ghost)} — {ghost['total']}")
    await message.reply("\n".join(lines))


# --- Anniversaires ---


def _parse_birthday(arg: str) -> tuple[int, int] | None:
    parts = arg.replace("-", "/").replace(".", "/").split("/")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    day, month = int(parts[0]), int(parts[1])
    try:
        date(2024, month, day)  # 2024 est bissextile : le 29/02 est accepté
    except ValueError:
        return None
    return day, month


def _next_birthday(day: int, month: int, today: date) -> date:
    for year in (today.year, today.year + 1, today.year + 2):
        try:
            candidate = date(year, month, day)
        except ValueError:  # 29/02 une année non bissextile : on fête le 28
            candidate = date(year, 2, 28)
        if candidate >= today:
            return candidate
    return today


@router.message(Command("anniv", "anniversaire", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_anniv(message: Message, command: CommandObject, db: Database) -> None:
    arg = (command.args or "").strip().lower()
    user_id = message.from_user.id
    if arg in ("off", "suppr", "supprimer"):
        await db.delete_birthday(user_id)
        await message.reply("🎂 Anniversaire supprimé.")
        return
    if not arg:
        row = await db.get_birthday(user_id)
        if row:
            await message.reply(f"🎂 {row['day']} {MONTHS[row['month'] - 1]}")
        else:
            await message.reply("Usage : <code>/anniv JJ/MM</code>")
        return
    parsed = _parse_birthday(arg)
    if parsed is None:
        await message.reply("Usage : <code>/anniv JJ/MM</code>")
        return
    await db.set_birthday(user_id, *parsed)
    await message.reply(f"🎂 Noté : {parsed[0]} {MONTHS[parsed[1] - 1]}")


@router.message(Command("anniversaires", "annivs", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_anniversaires(message: Message, db: Database, cfg: Config) -> None:
    today = datetime.now(cfg.tz).date()
    rows = await db.all_birthdays()
    if not rows:
        await message.reply("🎂 Aucun anniversaire.")
        return
    upcoming = sorted(rows, key=lambda row: _next_birthday(row["day"], row["month"], today))[:10]
    lines = ["<b>🎂 Prochains anniversaires</b>"]
    for row in upcoming:
        when = _next_birthday(row["day"], row["month"], today)
        days = (when - today).days
        delay = "aujourd'hui ! 🎉" if days == 0 else "demain" if days == 1 else f"dans {days} jours"
        lines.append(f"• {_who(row)} — {row['day']} {MONTHS[row['month'] - 1]} ({delay})")
    await message.reply("\n".join(lines))


async def wish_birthdays(bot: Bot, db: Database, cfg: Config) -> None:
    """Souhaite les anniversaires du jour (une seule fois par jour, même après un redémarrage)."""
    today = datetime.now(cfg.tz).date()
    if await db.get_setting("anniv_last") == today.isoformat():
        return
    await db.set_setting("anniv_last", today.isoformat())
    leap_fallback = today.month == 2 and today.day == 28 and not _is_leap(today.year)
    people = [
        row for row in await db.all_birthdays()
        if (row["day"], row["month"]) == (today.day, today.month) or (leap_fallback and (row["day"], row["month"]) == (29, 2))
    ]
    for row in people:
        try:
            await bot.send_message(
                cfg.chat_id, f"🎂 <b>Joyeux anniversaire {_who(row)} !</b> 🎉"
            )
        except TelegramAPIError as exc:
            log.warning("Anniversaire de %s non souhaité : %s", row["user_id"], exc)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


async def birthday_loop(bot: Bot, db: Database, cfg: Config) -> None:
    """Tourne en fond : vérifie au démarrage, puis chaque jour à minuit (heure du groupe)."""
    while True:
        try:
            await wish_birthdays(bot, db, cfg)
        except Exception:
            log.exception("Échec des anniversaires")
        now = datetime.now(cfg.tz)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
        await asyncio.sleep((midnight - now).total_seconds())
