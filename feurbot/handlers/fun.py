"""Le coin des blagues nulles (et assumées)."""

import random

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..db import Database
from ..filters import IsAdmin, IsMember
from ..jokes import EIGHTBALL, JOKES
from ..utils import PREFIXES, on_cooldown

router = Router(name="fun")

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
