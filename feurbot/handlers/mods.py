"""Modos : nommés par les admins du bot, ils peuvent sanctionner mais pas configurer le bot."""

import logging
import time

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database, full_name
from ..filters import IsAdmin, IsMember
from ..targets import Target, resolve_target
from ..utils import PREFIXES, format_date, mention, send_log

log = logging.getLogger(__name__)

router = Router(name="mods")

async def _target(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config, usage: str):
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error or target is None:
        await message.reply(error or f"Usage : <code>{usage}</code> ou en réponse à un message.")
        return None
    return target


@router.message(Command("mod", "modo", "promote", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_mod(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    target = await _target(message, command, bot, db, cfg, ".mod @pseudo|ID")
    if target is None:
        return
    if target.id == bot.id:
        await message.reply("🙃 Me nommer modo ? Je suis déjà au-dessus de tout ça.")
        return
    if target.id in cfg.admin_ids:
        await message.reply(f"👑 {target.mention} est déjà admin du bot. Le rétrograder en modo, ce serait cruel.")
        return
    if not await db.add_mod(target.id, message.from_user.id):
        await message.reply(f"ℹ️ {target.mention} est déjà modo. On ne peut pas être modo deux fois, même avec du talent.")
        return

    await db.add_action("mod", target.id, message.from_user.id)
    log.info("%s nommé modo par %s", target.id, message.from_user.id)
    await message.reply(
        f"🛡 <b>{target.mention} est maintenant modo !</b>\n"
        "Il peut ban, mute, kick, warn, purge, épingler et voir les fiches.\n"
        "<i>Un grand pouvoir implique de grandes responsabilités. Et zéro « quoi ».</i>"
    )
    await send_log(
        bot,
        cfg,
        f"#MOD #id{target.id}\n<b>🛡 Nouveau modo</b>\n👤 {target.label}\n"
        f"👮 Par : {Target.from_user(message.from_user).label}\n🕒 {format_date(time.time(), cfg)}",
    )


@router.message(Command("unmod", "unmodo", "demod", "demote", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_unmod(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    target = await _target(message, command, bot, db, cfg, ".unmod @pseudo|ID")
    if target is None:
        return
    if not await db.remove_mod(target.id):
        await message.reply(f"ℹ️ {target.mention} n'est pas modo. Difficile de le virer d'un poste qu'il n'a pas.")
        return

    await db.add_action("unmod", target.id, message.from_user.id)
    log.info("%s n'est plus modo (par %s)", target.id, message.from_user.id)
    await message.reply(
        f"🪖 {target.mention} n'est plus modo.\n<i>Retour au rang de simple mortel. Merci pour tes services.</i>"
    )
    await send_log(
        bot,
        cfg,
        f"#UNMOD #id{target.id}\n<b>🪖 Plus modo</b>\n👤 {target.label}\n"
        f"👮 Par : {Target.from_user(message.from_user).label}\n🕒 {format_date(time.time(), cfg)}",
    )


@router.message(Command("mods", "modos", "staff", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_mods(message: Message, db: Database, cfg: Config) -> None:
    admins = []
    for admin_id in sorted(cfg.admin_ids):
        user = await db.get_user(admin_id)
        admins.append(mention(admin_id, full_name(user["first_name"], user["last_name"]) if user else str(admin_id)))

    lines = ["<b>👮 L'équipe de feurchat</b>", f"👑 Admins : {', '.join(admins)}"]
    mods = await db.list_mods()
    if mods:
        lines.append(f"🛡 Modos ({len(mods)}) :")
        for row in mods:
            name = full_name(row["first_name"], row["last_name"]) if row["first_name"] else str(row["user_id"])
            lines.append(f"• {mention(row['user_id'], name)} — depuis le {format_date(row['added_at'], cfg)}")
    else:
        lines.append("🛡 Modos : personne. Les admins font tout eux-mêmes, respect.")
    lines.append("\n<i>Un souci ? Réponds au message avec <code>.report</code>.</i>")
    await message.reply("\n".join(lines))
