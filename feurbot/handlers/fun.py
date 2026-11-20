"""Le coin des blagues nulles (et assumées)."""

import asyncio
import hashlib
import random
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database, full_name
from ..filters import IsAdmin, IsMember
from ..jokes import (
    COUPLE_QUIPS,
    EIGHTBALL,
    ELU_QUIPS,
    HACK_RESULTS,
    HACK_STEPS,
    INSULT_ADJECTIVES,
    INSULT_NOUNS,
    JOKES,
    iq_comment,
    love_comment,
)
from ..targets import Target, resolve_target
from ..utils import PREFIXES, mention, on_cooldown

router = Router(name="fun")

HACK_DELAY = 1.2  # secondes entre deux étapes du faux piratage
DICE = {"de": "🎲", "dé": "🎲", "dard": "🎯", "slot": "🎰", "casino": "🎰", "foot": "⚽", "basket": "🏀", "bowling": "🎳"}


def _spam(message: Message) -> bool:
    """Petite limite anti-spam : une commande fun toutes les 5 s par personne."""
    return on_cooldown(f"fun:{message.from_user.id}", 5)


@router.message(Command("blague", "joke", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_blague(message: Message) -> None:
    if not _spam(message):
        await message.reply(f"😂 {random.choice(JOKES)}")


@router.message(Command("pileouface", "pf", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_coin(message: Message) -> None:
    if _spam(message):
        return
    if random.random() < 0.03:
        await message.reply("🪙 La pièce est retombée sur la tranche. C'est un signe. Ou un bug.")
    else:
        await message.reply(f"🪙 {random.choice(['Pile', 'Face'])} !")


@router.message(Command(*DICE, prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_dice(message: Message, command: CommandObject) -> None:
    if not _spam(message):
        await message.reply_dice(emoji=DICE[command.command.lower()])


@router.message(Command("boule", "8ball", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_boule(message: Message, command: CommandObject) -> None:
    if _spam(message):
        return
    if not (command.args or "").strip():
        await message.reply("🎱 Faut poser une question, champion. <code>.boule je vais être admin ?</code>")
        return
    await message.reply(f"🎱 {random.choice(EIGHTBALL)}")


@router.message(Command("quoi", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_quoi(message: Message) -> None:
    if not _spam(message):
        await message.reply("feur. Évidemment.")


@router.message(Command("feur", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_feur(message: Message, command: CommandObject, db: Database) -> None:
    arg = (command.args or "").strip().lower()
    if arg in ("on", "off"):
        await db.set_setting("feur", arg == "on")
        await message.reply(
            "✅ Réponses « quoi → feur » activées. Que la chasse commence. 😈"
            if arg == "on"
            else "⛔️ Réponses « feur » désactivées. Triste époque."
        )
        return
    state = "activées ✅" if await db.get_setting("feur", True) else "désactivées ⛔️"
    await message.reply(
        f"Réponses automatiques « quoi → feur » : {state}\n"
        "<code>.feur on</code> / <code>.feur off</code>\n"
        "<i>Je réponds aussi à oui (stiti), non (bril), hein (deux), comment (dant)… une fois sur deux.</i>"
    )


# --- Tirages du jour ---


def _daily_score(db: Database, *parts: int, modulo: int) -> int:
    """Score stable pour la journée : relancer la commande ne change rien (pas de triche)."""
    seed = "|".join(map(str, (*parts, db.today()))).encode()
    return int.from_bytes(hashlib.sha256(seed).digest()[:4], "big") % modulo


async def _daily_pick(db: Database, key: str, count: int) -> list[int] | None:
    state = await db.get_setting(key, {})
    if state.get("date") == db.today():
        return state["ids"]
    candidates = await db.active_users(days=7)
    if len(candidates) < count:
        return None
    ids = random.sample(candidates, count)
    await db.set_setting(key, {"date": db.today(), "ids": ids})
    return ids


async def _mention_id(db: Database, user_id: int) -> str:
    row = await db.get_user(user_id)
    return mention(user_id, full_name(row["first_name"], row["last_name"]) if row else str(user_id))


@router.message(Command("couple", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_couple(message: Message, db: Database) -> None:
    if _spam(message):
        return
    ids = await _daily_pick(db, "couple", 2)
    if ids is None:
        await message.reply("💔 Pas assez de monde actif pour former un couple. Parlez un peu, timides.")
        return
    a, b = [await _mention_id(db, user_id) for user_id in ids]
    await message.reply(f"💘 <b>Couple du jour</b>\n{a} ❤️ {b}\n\n<i>{random.choice(COUPLE_QUIPS)}</i>")


@router.message(Command("elu", "élu", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_elu(message: Message, db: Database) -> None:
    if _spam(message):
        return
    ids = await _daily_pick(db, "elu", 1)
    if ids is None:
        await message.reply("👑 Personne à élire. Le trône reste vide, comme vos conversations.")
        return
    await message.reply(
        f"👑 <b>Le boloss du jour</b> est… {await _mention_id(db, ids[0])} !\n\n<i>{random.choice(ELU_QUIPS)}</i>"
    )


@router.message(Command("love", "amour", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_love(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    if _spam(message):
        return
    first, rest, error = await resolve_target(message, command.args or "", bot, db, cfg)
    second, _, error2 = await resolve_target(message, rest, bot, db, cfg) if first and rest.strip() else (None, "", None)
    if error or error2 or first is None:
        await message.reply(error or error2 or "💘 Usage : <code>.love @a @b</code>, ou <code>.love @pseudo</code> pour toi et lui.")
        return
    if second is None:
        first, second = Target.from_user(message.from_user), first
    if first.id == second.id:
        await message.reply(f"🪞 {first.mention} + {second.mention} : 100 %. L'amour-propre, c'est important.")
        return
    score = _daily_score(db, *sorted((first.id, second.id)), modulo=101)
    await message.reply(f"💘 {first.mention} + {second.mention} : <b>{score} %</b>\n{love_comment(score)}")


@router.message(Command("qi", "iq", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_qi(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    if _spam(message):
        return
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error:
        await message.reply(error)
        return
    target = target or Target.from_user(message.from_user)
    if target.id == bot.id:
        await message.reply("🧠 Mon QI : 9000. Évidemment. Question suivante.")
        return
    score = _daily_score(db, target.id, modulo=200)
    await message.reply(f"🧠 QI de {target.mention} aujourd'hui : <b>{score}</b>\n{iq_comment(score)}")


@router.message(Command("hack", "pirater", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_hack(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    if on_cooldown(f"hack:{message.from_user.id}", 30):
        return
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error or target is None:
        await message.reply(error or "💻 Usage : <code>.hack @pseudo</code> ou en réponse à ta victime.")
        return
    if target.id == bot.id:
        await message.reply("💻 Me pirater ? Je tourne sur un serveur à 2 €. Y a rien à voler.")
        return
    sent = await message.reply(HACK_STEPS[0].format(name=escape(target.name)))
    for step in HACK_STEPS[1:]:
        await asyncio.sleep(HACK_DELAY)
        await sent.edit_text(step.format(name=escape(target.name)))
    await asyncio.sleep(HACK_DELAY)
    found = "\n".join(f"• {line}" for line in random.sample(HACK_RESULTS, 2))
    await sent.edit_text(
        f"✅ <b>Piratage de {target.mention} terminé.</b>\n{found}\n\n<i>Données revendues 2 € sur le dark web. Feur.</i>"
    )


@router.message(Command("clash", "insulte", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_clash(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    if _spam(message):
        return
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error or target is None:
        await message.reply(error or "⚔️ Usage : <code>.clash @pseudo</code> ou en réponse. Je fournis les munitions.")
        return
    if target.id == bot.id:
        await message.reply("⚔️ Tu veux me clasher ? Espèce de… non, je suis au-dessus de ça. Paltoquet.")
        return
    insult = f"{random.choice(INSULT_NOUNS)} {random.choice(INSULT_ADJECTIVES)}"
    bonus = " Et en plus tu dis « quoi »." if random.random() < 0.3 else ""
    await message.reply(f"⚔️ {target.mention}, espèce de <b>{insult}</b> !{bonus}")


@router.message(Command("moqueur", "mock", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_moqueur(message: Message) -> None:
    reply = message.reply_to_message
    original = (reply.text or reply.caption) if reply and message.chat.type != ChatType.PRIVATE else None
    if not original:
        await message.reply("🧽 Réponds au message à imiter. Je ne vais pas me moquer du vide.")
        return
    if _spam(message):
        return
    chars, upper = [], False
    for char in original[:1000]:
        if char.isalpha():
            char = char.upper() if upper else char.lower()
            upper = not upper
        chars.append(char)
    await reply.reply(f"🧽 « {escape(''.join(chars))} »")
