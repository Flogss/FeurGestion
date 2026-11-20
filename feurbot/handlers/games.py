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
from ..targets import Target, resolve_target
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
        await message.reply("🔫 La roulette, ça se joue en public. Sinon c'est pas drôle.")
        return
    if not await games_on(db):
        await message.reply("🎮 Les jeux sont désactivés. Les admins ont eu peur de perdre.")
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
        await message.reply("⚔️ Un duel en privé ? Contre qui, ton reflet ?")
        return
    if not await games_on(db):
        await message.reply("🎮 Les jeux sont désactivés. Rangez les armes.")
        return
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error or target is None:
        await message.reply(error or "⚔️ Usage : <code>.duel @pseudo</code> ou en réponse à ta future victime.")
        return
    if target.id == message.from_user.id:
        await message.reply("⚔️ Un duel contre toi-même ? Tu vas perdre. Et gagner. C'est compliqué.")
        return
    if target.id == bot.id:
        await message.reply("⚔️ Me défier, moi ? J'ai des balles infinies et zéro sentiment.")
        return
    if on_cooldown(f"duel:{message.from_user.id}", 30):
        return
    challenger = Target.from_user(message.from_user).mention
    await message.reply(
        f"⚔️ {challenger} provoque {target.mention} en duel !\n"
        "Le perdant prend 1 minute de mute.\n"
        f"{target.mention}, tu as 5 minutes pour accepter. Ou fuir, on juge pas. (Si, on juge.)",
        reply_markup=_duel_keyboard(message.from_user.id, target.id),
    )


@router.callback_query(F.data.startswith("duel:"))
async def on_duel(callback: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    _, choice, challenger, opponent, created = callback.data.split(":")
    challenger, opponent, created = int(challenger), int(opponent), int(created)
    if callback.from_user.id != opponent:
        await callback.answer("🍿 Ce duel ne te concerne pas. Prends du pop-corn et regarde.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    a = mention(challenger, await _name(db, challenger))
    b = mention(opponent, full_name(callback.from_user.first_name, callback.from_user.last_name))
    if time.time() - created > DUEL_TIMEOUT:
        await callback.message.edit_text(f"⌛ Duel expiré. {b} a mis trop de temps. Courage, fuyons.", reply_markup=None)
        await callback.answer()
        return
    if choice == "no":
        await callback.message.edit_text(f"🏳️ {b} refuse le duel contre {a}. Poule mouillée 🐔", reply_markup=None)
        await callback.answer("Fuite enregistrée. 🐔")
        return

    loser = random.choice([challenger, opponent])
    winner_tag, loser_tag = (b, a) if loser == challenger else (a, b)
    lines = [f"⚔️ <b>Duel : {a} contre {b}</b>", "🔫 3… 2… 1… PAN !"]
    if await game_mute(loser, "duel", bot, db, cfg):
        lines += [f"💀 {loser_tag} tombe. 1 minute de mute.", f"🏆 {winner_tag} remporte le duel. Respect."]
    else:
        lines += [f"🛡 {loser_tag} est touché… mais admin, donc gilet pare-balles.", "Personne ne meurt. C'est nul."]
    await callback.message.edit_text("\n".join(lines), reply_markup=None)
    await callback.answer()


# --- Prison ---


@router.message(Command("prison", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_prison(message: Message, db: Database) -> None:
    rows = await db.prisoners()
    if not rows:
        await message.reply("🚔 La prison est vide. Soit vous êtes sages, soit les modos dorment.")
        return
    now = int(time.time())
    lines = [f"🚔 <b>Quartier haute sécurité de feurchat</b> — {len(rows)} détenu(s)"]
    for row in rows:
        name = full_name(row["first_name"], row["last_name"]) if row["first_name"] else str(row["user_id"])
        icon = ACTION_LABELS[row["action"]].split()[0]
        remaining = f"encore {format_duration(row['until'] - now)}" if row["until"] else "à perpétuité"
        reason = f" — {escape(row['reason'])}" if row["reason"] else ""
        lines.append(f"{icon} {mention(row['user_id'], name)} : {remaining}{reason}")
    lines.append("\n<i>Les visites sont interdites. Les gâteaux avec une lime dedans aussi.</i>")
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
    lines = [f"💥 <b>BOOM !</b> {who} a dit le mot interdit du jour : « <b>{escape(state['word'])}</b> »."]
    if await game_mute(user.id, "mot interdit", bot, db, cfg):
        lines.append("1 minute de silence. 🤐")
    else:
        lines.append("…mais admin, donc immunisé. Scandale.")
    lines.append("<i>Prochain mot interdit : demain. Faites gaffe à ce que vous dites.</i>")
    await message.reply("\n".join(lines))
    log.info("Mot interdit « %s » trouvé par %s", state["word"], user.id)
    return True


@router.message(Command("motinterdit", "mot", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_motinterdit(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    arg = (command.args or "").strip().lower()
    is_admin = message.from_user.id in cfg.admin_ids
    if arg in ("on", "off"):
        if not is_admin:
            await message.reply("🤫 Bien essayé, mais seuls les admins peuvent désamorcer la bombe.")
            return
        await db.set_setting("motinterdit_on", arg == "on")
        await message.reply(
            "💣 Mot interdit du jour activé. Que la paranoïa commence."
            if arg == "on"
            else "🧯 Mot interdit désactivé. Vous pouvez parler librement. Enfin, presque."
        )
        return
    if not await db.get_setting("motinterdit_on", True):
        await message.reply("🧯 Le mot interdit est désactivé. <code>.motinterdit on</code> pour le réveiller (admins).")
        return

    state = await forbidden_state(db)
    if state["found_by"]:
        who = mention(state["found_by"], await _name(db, state["found_by"]))
        await message.reply(f"💥 Déjà trouvé aujourd'hui par {who} : « {escape(state['word'])} ». Prochain mot demain.")
    elif is_admin and message.chat.type == ChatType.PRIVATE:
        await message.reply(f"🤫 Entre nous : le mot interdit du jour est « <b>{escape(state['word'])}</b> ». Chut.")
    else:
        await message.reply(
            "🤫 Il y a un mot interdit aujourd'hui. Personne ne l'a encore dit.\n"
            "Celui qui le dit prend 1 minute de mute. Bonne conversation. 😇"
        )


@router.message(Command("jeux", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_jeux(message: Message, command: CommandObject, db: Database) -> None:
    arg = (command.args or "").strip().lower()
    if arg in ("on", "off"):
        await db.set_setting("jeux", arg == "on")
        await message.reply(
            "🎮 Jeux activés : roulette et duels sont ouverts. Que le meilleur survive."
            if arg == "on"
            else "🎮 Jeux désactivés. Fini de rire. Enfin, moins."
        )
        return
    state = "activés ✅" if await games_on(db) else "désactivés ⛔️"
    await message.reply(f"🎮 Roulette et duels : {state}\n<code>.jeux on</code> / <code>.jeux off</code>")
