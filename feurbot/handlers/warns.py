import logging
import time
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import Config
from ..db import Database
from ..filters import IsAdmin, IsMember, IsStaff, is_staff
from ..jokes import quip
from ..targets import Target, reply_error, resolve_target
from ..utils import ACTION_LABELS, PREFIXES, format_date, format_duration, send_log, shorten
from .moderation import apply_sanction, check_target

log = logging.getLogger(__name__)

router = Router(name="warns")

DEFAULT_WARN = {"limit": 3, "action": "mute"}
LIMIT_ACTIONS = {"mute": 86400, "ban": None, "kick": None}  # durée du mute automatique : 24 h


async def get_warn_conf(db: Database) -> dict:
    return {**DEFAULT_WARN, **await db.get_setting("warn", {})}


def _remove_keyboard(warn_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🧽 Retirer le warn", callback_data=f"unwarn:{warn_id}")]]
    )


@router.message(Command("warn", prefix=PREFIXES, ignore_case=True), IsStaff())
async def cmd_warn(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    target, rest, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error:
        await reply_error(message, error)
        return
    if target is None:
        await message.reply("Usage : <code>/warn @pseudo|ID [raison]</code>")
        return
    problem = await check_target("warn", target, message.from_user.id, bot, cfg, db)
    if problem:
        await message.reply(problem)
        return

    admin = message.from_user
    reason = rest.strip() or None
    warn_id = await db.add_warn(target.id, admin.id, reason)
    await db.add_action("warn", target.id, admin.id, reason)
    conf = await get_warn_conf(db)
    count = len(await db.user_warns(target.id))
    log.info("warn %s par %s (%s/%s)", target.id, admin.id, count, conf["limit"])

    lines = [f"<b>⚠️ Warn {count}/{conf['limit']}</b> — {target.mention}"]
    if reason:
        lines.append(f"📝 {escape(reason)}")
    log_lines = [
        f"#WARN #id{target.id}", f"👤 {target.label}", *lines[1:],
        f"🔢 {count}/{conf['limit']}", f"👮 Par : {Target.from_user(admin).label}",
    ]

    if count < conf["limit"]:
        lines.append(f"<i>{quip('warn')}</i>")
        await message.reply("\n".join(lines), reply_markup=_remove_keyboard(warn_id))
        await send_log(bot, cfg, "\n".join(log_lines))
        return

    # Limite atteinte : sanction automatique puis remise à zéro du compteur
    action = conf["action"]
    duration = LIMIT_ACTIONS[action]
    until = int(time.time()) + duration if duration else None
    sanction_reason = f"{conf['limit']} warns"
    try:
        await apply_sanction(action, target.id, until, bot, cfg)
    except TelegramAPIError as exc:
        await message.reply("\n".join(lines) + f"\n❌ Telegram : {escape(exc.message)}")
        return
    await db.add_action(action, target.id, admin.id, sanction_reason, duration, until)
    await db.clear_warns(target.id)

    label = ACTION_LABELS[action] + (f" {format_duration(duration)}" if duration else "")
    lines[0] = f"<b>🟥 Warn {count}/{conf['limit']} → {label}</b> — {target.mention}"
    lines.append(f"<i>{quip('warn_limit')}</i>")
    await message.reply("\n".join(lines))
    await send_log(bot, cfg, "\n".join(log_lines) + f"\n➡️ {label} automatique")


@router.message(Command("unwarn", "rmwarn", prefix=PREFIXES, ignore_case=True), IsStaff())
async def cmd_unwarn(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error or target is None:
        await reply_error(message, error, "Usage : <code>/unwarn @pseudo|ID</code>")
        return
    warns = await db.user_warns(target.id)
    if not warns:
        await message.reply(f"ℹ️ {target.mention} n'a aucun warn.")
        return
    await db.remove_warn(warns[-1]["id"])
    await db.add_action("unwarn", target.id, message.from_user.id)
    conf = await get_warn_conf(db)
    await message.reply(f"🧽 {target.mention} : {len(warns) - 1}/{conf['limit']}")


@router.message(Command("resetwarns", prefix=PREFIXES, ignore_case=True), IsStaff())
async def cmd_resetwarns(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error or target is None:
        await reply_error(message, error, "Usage : <code>/resetwarns @pseudo|ID</code>")
        return
    removed = await db.clear_warns(target.id)
    if removed:
        await db.add_action("unwarn", target.id, message.from_user.id, "remise à zéro")
    await message.reply(f"🧼 {target.mention} : 0/{(await get_warn_conf(db))['limit']}")


@router.message(Command("warnlimit", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_warnlimit(message: Message, command: CommandObject, db: Database) -> None:
    conf = await get_warn_conf(db)
    arg = (command.args or "").strip()
    if not arg.isdigit() or not 1 <= int(arg) <= 20:
        await message.reply(f"⚠️ Limite : <b>{conf['limit']}</b> warns (<code>/warnlimit 1-20</code>)")
        return
    conf["limit"] = int(arg)
    await db.set_setting("warn", conf)
    await message.reply(f"✅ Limite : <b>{conf['limit']}</b> warns")


@router.message(Command("warnaction", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_warnaction(message: Message, command: CommandObject, db: Database) -> None:
    conf = await get_warn_conf(db)
    arg = (command.args or "").strip().lower()
    if arg not in LIMIT_ACTIONS:
        await message.reply(
            f"⚠️ À la limite : <b>{conf['action']}</b> (<code>/warnaction mute|ban|kick</code>)"
        )
        return
    conf["action"] = arg
    await db.set_setting("warn", conf)
    await message.reply(f"✅ À la limite : <b>{arg}</b>")


@router.message(Command("warns", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_warns(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error:
        await reply_error(message, error)
        return
    target = target or Target.from_user(message.from_user)
    warns = await db.user_warns(target.id)
    conf = await get_warn_conf(db)
    if not warns:
        await message.reply(f"😇 {target.mention} : 0/{conf['limit']}")
        return
    lines = [f"<b>⚠️ Warns de {target.mention} : {len(warns)}/{conf['limit']}</b>"]
    for warn in warns:
        reason = escape(shorten(warn["reason"])) if warn["reason"] else "sans raison"
        lines.append(f"• {format_date(warn['created_at'], cfg)} — {reason}")
    await message.reply("\n".join(lines))


@router.callback_query(F.data.startswith("unwarn:"))
async def on_unwarn(callback: CallbackQuery, db: Database, cfg: Config) -> None:
    if not await is_staff(callback.from_user.id, cfg, db):
        await callback.answer("⛔️ Réservé à l'équipe.", show_alert=True)
        return
    warn = await db.get_warn(int(callback.data.removeprefix("unwarn:")))
    if warn is None or not await db.remove_warn(warn["id"]):
        await callback.answer("Ce warn n'existe plus.", show_alert=True)
        return
    await db.add_action("unwarn", warn["user_id"], callback.from_user.id, f"annulation du warn #{warn['id']}")
    await callback.answer("✅ Warn retiré")
    if isinstance(callback.message, Message):
        note = f"🧽 Retiré par {Target.from_user(callback.from_user).mention}"
        await callback.message.edit_text(f"{callback.message.html_text}\n\n{note}", reply_markup=None)
