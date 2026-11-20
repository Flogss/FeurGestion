"""Jeux qui piquent un peu : roulette, duel, mot interdit du jour, et la prison pour voir les dégâts."""

import logging
import random
import re
import time
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User

from ..config import Config
from ..db import Database, full_name
from ..filters import IsAdmin, IsMember
from ..jokes import FORBIDDEN_WORDS, ROULETTE_ARMORED, ROULETTE_DEAD, ROULETTE_SAFE
from ..targets import Target, reply_error, resolve_target
from ..utils import ACTION_LABELS, PREFIXES, format_duration, group_admin_ids, mention, on_cooldown
from .moderation import apply_sanction

log = logging.getLogger(__name__)

router = Router(name="games")

GAME_MUTE = 60  # secondes
DUEL_TIMEOUT = 300


async def games_on(db: Database) -> bool:
    return await db.get_setting("jeux", True)


async def game_mute(user_id: int, reason: str, bot: Bot, db: Database, cfg: Config) -> bool:
    """Mute de jeu d'une minute. False si la personne est admin Telegram (intouchable)."""
    if user_id in await group_admin_ids(bot, cfg):
        return False
    until = int(time.time()) + GAME_MUTE
    try:
        await apply_sanction("mute", user_id, until, bot, cfg)
    except TelegramAPIError as exc:
        log.warning("Mute de jeu impossible pour %s : %s", user_id, exc)
        return False
    await db.add_action("jail", user_id, None, reason, GAME_MUTE, until)
    return True


async def _name(db: Database, user_id: int) -> str:
    row = await db.get_user(user_id)
    return full_name(row["first_name"], row["last_name"]) if row else str(user_id)


# --- Roulette ---


@router.message(Command("roulette", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_roulette(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    if message.chat.type == ChatType.PRIVATE:
        await message.reply("🔫 Pas en privé.")
        return
    if not await games_on(db):
        await message.reply("🎮 Jeux désactivés.")
        return
    if on_cooldown(f"roulette:{message.from_user.id}", 10):
        return
    if random.randint(1, 6) != 1:
        await message.reply(random.choice(ROULETTE_SAFE))
        return
    who = Target.from_user(message.from_user).mention
    if await game_mute(message.from_user.id, "roulette", bot, db, cfg):
        await message.reply(random.choice(ROULETTE_DEAD).format(mention=who))
    else:
        await message.reply(ROULETTE_ARMORED.format(mention=who))


# --- Duel ---


def _duel_keyboard(challenger: int, opponent: int) -> InlineKeyboardMarkup:
    base = f"{challenger}:{opponent}:{int(time.time())}"
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="⚔️ J'accepte", callback_data=f"duel:ok:{base}"),
            InlineKeyboardButton(text="🏳️ Je fuis", callback_data=f"duel:no:{base}"),
        ]]
    )


@router.message(Command("duel", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_duel(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    if message.chat.type == ChatType.PRIVATE:
        await message.reply("⚔️ Pas en privé.")
        return
    if not await games_on(db):
        await message.reply("🎮 Jeux désactivés.")
        return
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error or target is None:
        await reply_error(message, error, "Usage : <code>/duel @pseudo</code>")
        return
    if target.id == message.from_user.id:
        await message.reply("⚔️ Contre toi-même ?")
        return
    if target.id == bot.id:
        await message.reply("⚔️ Contre moi ? Non.")
        return
    if on_cooldown(f"duel:{message.from_user.id}", 30):
        return
    challenger = Target.from_user(message.from_user).mention
    await message.reply(
        f"⚔️ {challenger} défie {target.mention} — le perdant est mute 1 min",
        reply_markup=_duel_keyboard(message.from_user.id, target.id),
    )


@router.callback_query(F.data.startswith("duel:"))
async def on_duel(callback: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    _, choice, challenger, opponent, created = callback.data.split(":")
    challenger, opponent, created = int(challenger), int(opponent), int(created)
    if callback.from_user.id != opponent:
        await callback.answer("🍿 Pas ton duel.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    a = mention(challenger, await _name(db, challenger))
    b = mention(opponent, full_name(callback.from_user.first_name, callback.from_user.last_name))
    if time.time() - created > DUEL_TIMEOUT:
        await callback.message.edit_text("⌛ Duel expiré.", reply_markup=None)
        await callback.answer()
        return
    if choice == "no":
        await callback.message.edit_text(f"🏳️ {b} refuse. 🐔", reply_markup=None)
        await callback.answer("🐔")
        return

    loser = random.choice([challenger, opponent])
    winner_tag, loser_tag = (b, a) if loser == challenger else (a, b)
    lines = [f"⚔️ {a} contre {b} — PAN !"]
    if await game_mute(loser, "duel", bot, db, cfg):
        lines.append(f"💀 {loser_tag} (1 min de mute) · 🏆 {winner_tag}")
    else:
        lines.append(f"🛡 {loser_tag} est admin : aucun effet")
    await callback.message.edit_text("\n".join(lines), reply_markup=None)
    await callback.answer()


# --- Prison ---


@router.message(Command("prison", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_prison(message: Message, db: Database) -> None:
    rows = await db.prisoners()
    if not rows:
        await message.reply("🚔 Prison vide.")
        return
    now = int(time.time())
    lines = ["🚔 <b>Prison</b>"]
    for row in rows:
        name = full_name(row["first_name"], row["last_name"]) if row["first_name"] else str(row["user_id"])
        icon = ACTION_LABELS[row["action"]].split()[0]
        remaining = format_duration(row["until"] - now) if row["until"] else "à vie"
        reason = f" — {escape(row['reason'])}" if row["reason"] else ""
        lines.append(f"{icon} {mention(row['user_id'], name)} : {remaining}{reason}")
    await message.reply("\n".join(lines))


# --- Mot interdit du jour ---


async def forbidden_state(db: Database) -> dict:
    state = await db.get_setting("motinterdit", {})
    if state.get("date") != db.today():
        choices = [word for word in FORBIDDEN_WORDS if word != state.get("word")]
        state = {"date": db.today(), "word": random.choice(choices), "found_by": None}
        await db.set_setting("motinterdit", state)
    return state


async def check_forbidden_word(message: Message, bot: Bot, db: Database, cfg: Config) -> bool:
    """Si le message contient le mot interdit du jour : BOOM. Retourne True si ça a explosé."""
    if not await db.get_setting("motinterdit_on", True):
        return False
    state = await forbidden_state(db)
    text = message.text or message.caption or ""
    if state["found_by"] or not re.search(rf"(?<!\w){re.escape(state['word'])}(?!\w)", text, re.I):
        return False

    user: User = message.from_user
    state["found_by"] = user.id
    await db.set_setting("motinterdit", state)
    who = Target.from_user(user).mention
    muted = await game_mute(user.id, "mot interdit", bot, db, cfg)
    effect = "1 min de mute" if muted else "admin, immunisé"
    await message.reply(f"💥 <b>BOOM !</b> {who} a dit « <b>{escape(state['word'])}</b> » — {effect}")
    log.info("Mot interdit « %s » trouvé par %s", state["word"], user.id)
    return True


@router.message(Command("motinterdit", "mot", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_motinterdit(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    arg = (command.args or "").strip().lower()
    is_admin = message.from_user.id in cfg.admin_ids
    if arg in ("on", "off"):
        if not is_admin:
            await message.reply("🤫 Réservé aux admins.")
            return
        await db.set_setting("motinterdit_on", arg == "on")
        await message.reply(
            "💣 Mot interdit activé" if arg == "on" else "🧯 Mot interdit désactivé"
        )
        return
    if not await db.get_setting("motinterdit_on", True):
        await message.reply("🧯 Mot interdit désactivé.")
        return

    state = await forbidden_state(db)
    if state["found_by"]:
        who = mention(state["found_by"], await _name(db, state["found_by"]))
        await message.reply(f"💥 Trouvé par {who} : « {escape(state['word'])} »")
    elif is_admin and message.chat.type == ChatType.PRIVATE:
        await message.reply(f"🤫 « <b>{escape(state['word'])}</b> »")
    else:
        await message.reply(
            "🤫 Un mot est interdit aujourd'hui : celui qui le dit prend 1 min de mute."
        )


@router.message(Command("jeux", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_jeux(message: Message, command: CommandObject, db: Database) -> None:
    arg = (command.args or "").strip().lower()
    if arg in ("on", "off"):
        await db.set_setting("jeux", arg == "on")
        await message.reply(
            "🎮 Jeux activés" if arg == "on" else "🎮 Jeux désactivés"
        )
        return
    state = "activés ✅" if await games_on(db) else "désactivés ⛔️"
    await message.reply(f"🎮 Jeux : {state}")
