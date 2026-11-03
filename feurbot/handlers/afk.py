"""AFK : « je m'absente », et le bot prévient ceux qui te mentionnent."""

import re
import time
from html import escape

from aiogram import Bot, Router
from aiogram.enums import MessageEntityType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database, full_name
from ..filters import IsMember
from ..targets import Target
from ..utils import PREFIXES, format_duration, mention, on_cooldown

router = Router(name="afk")

AFK_COMMAND = re.compile(r"^[.!/]afk\b", re.I)
BRB = re.compile(r"^brb\b\s*(.*)", re.I | re.S)


def _since(row) -> str:
    return format_duration(max(int(time.time()) - row["since"], 1))


async def _go_afk(message: Message, reason: str | None, db: Database) -> None:
    await db.set_afk(message.from_user.id, reason)
    who = Target.from_user(message.from_user).mention
    suffix = f" : {escape(reason)}" if reason else ""
    await message.reply(f"💤 {who} est AFK{suffix}.\n<i>On garde ta place au chaud. Enfin, on essaie.</i>")


@router.message(Command("afk", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_afk(message: Message, command: CommandObject, db: Database) -> None:
    await _go_afk(message, (command.args or "").strip() or None, db)


async def check(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    """Appelé pour chaque message du groupe : retour d'AFK, et prévient si on parle à quelqu'un d'AFK."""
    user = message.from_user
    text = message.text or message.caption or ""

    if AFK_COMMAND.match(text):
        return
    brb = BRB.match(text)
    if brb:
        await _go_afk(message, brb.group(1).strip() or None, db)
        return

    back = await db.clear_afk(user.id)
    if back:
        await message.reply(
            f"👋 Re {Target.from_user(user).mention} ! T'étais AFK depuis {_since(back)}.\n"
            "<i>On n'a pas trop parlé de toi, promis.</i>"
        )

    mentioned: set[int] = set()
    reply = message.reply_to_message
    if reply and reply.from_user:
        mentioned.add(reply.from_user.id)
    for entity in message.entities or message.caption_entities or []:
        if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
            mentioned.add(entity.user.id)
        elif entity.type == MessageEntityType.MENTION:
            row = await db.find_by_username(entity.extract_from(text))
            if row:
                mentioned.add(row["user_id"])
    mentioned.discard(user.id)

    for user_id in mentioned:
        row = await db.get_afk(user_id)
        if row is None or on_cooldown(f"afk:{user_id}", 60):
            continue
        known = await db.get_user(user_id)
        name = full_name(known["first_name"], known["last_name"]) if known else str(user_id)
        reason = f" : {escape(row['reason'])}" if row["reason"] else ""
        await message.reply(
            f"💤 {mention(user_id, name)} est AFK depuis {_since(row)}{reason}.\n"
            "<i>Laisse un message après le bip. Biiip.</i>"
        )
