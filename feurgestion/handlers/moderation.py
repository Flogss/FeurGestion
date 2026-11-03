import logging
import time
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatPermissions, Message

from ..config import Config
from ..db import Database
from ..filters import IsAdmin
from ..targets import Target, resolve_target
from ..utils import (
    ACTION_LABELS,
    MAX_DURATION,
    MIN_DURATION,
    PREFIXES,
    format_date,
    format_duration,
    in_chat,
    message_link,
    send_log,
    split_duration,
)

log = logging.getLogger(__name__)

router = Router(name="moderation")
router.message.filter(IsAdmin())

MUTED = ChatPermissions(**{field: False for field in ChatPermissions.model_fields})
ALL_ALLOWED = ChatPermissions(**{field: True for field in ChatPermissions.model_fields})

USAGE = {
    "ban": ".ban @pseudo|ID [durée] [raison]",
    "unban": ".unban @pseudo|ID",
    "mute": ".mute @pseudo|ID [durée] [raison]",
    "unmute": ".unmute @pseudo|ID",
    "kick": ".kick @pseudo|ID [raison]",
}
TIMED = ("ban", "mute")
PUNISHMENTS = ("ban", "mute", "kick")


async def _check_target(action: str, target: Target, admin_id: int, bot: Bot, cfg: Config) -> str | None:
    if target.id == bot.id:
        return "🙃 Je ne vais pas me sanctionner moi-même."
    if action in PUNISHMENTS:
        if target.id == admin_id:
            return "🙃 Tu ne peux pas te sanctionner toi-même."
        if target.id in cfg.admin_ids:
            return "❌ C'est un admin du bot."

    try:
        member = await bot.get_chat_member(cfg.chat_id, target.id)
    except TelegramAPIError:
        return None  # Telegram ne le connaît pas dans ce groupe : on tente quand même

    if action in PUNISHMENTS and member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
        return "❌ Impossible : c'est un admin du groupe."
    if action == "kick" and not in_chat(member):
        return "ℹ️ Il n'est pas dans le groupe."
    if action == "unban" and member.status != ChatMemberStatus.KICKED:
        return "ℹ️ Il n'est pas banni."
    if action == "unmute" and not (member.status == ChatMemberStatus.RESTRICTED and not member.can_send_messages):
        return "ℹ️ Il n'est pas mute."
    return None


async def _apply(action: str, user_id: int, until: int | None, bot: Bot, cfg: Config) -> None:
    if action == "ban":
        await bot.ban_chat_member(cfg.chat_id, user_id, until_date=until)
    elif action == "kick":
        # Ban puis unban immédiat : expulsé mais peut revenir avec un lien
        await bot.ban_chat_member(cfg.chat_id, user_id)
        await bot.unban_chat_member(cfg.chat_id, user_id, only_if_banned=True)
    elif action == "unban":
        await bot.unban_chat_member(cfg.chat_id, user_id, only_if_banned=True)
    elif action == "mute":
        await bot.restrict_chat_member(
            cfg.chat_id, user_id, MUTED, until_date=until, use_independent_chat_permissions=True
        )
    elif action == "unmute":
        # On rend les droits par défaut du groupe, pas plus
        chat = await bot.get_chat(cfg.chat_id)
        await bot.restrict_chat_member(
            cfg.chat_id, user_id, chat.permissions or ALL_ALLOWED, use_independent_chat_permissions=True
        )


@router.message(Command(*USAGE, prefix=PREFIXES, ignore_case=True))
async def cmd_sanction(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    action = command.command.lower()
    target, rest, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error:
        await message.reply(error)
        return
    if target is None:
        await message.reply(
            f"Usage : <code>{escape(USAGE[action])}</code>\nOu réponds à un message de la personne."
        )
        return

    duration = None
    if action in TIMED:
        duration, rest = split_duration(rest)
        if duration is not None and not MIN_DURATION <= duration <= MAX_DURATION:
            await message.reply("❌ La durée doit être entre 30s et 366j (sans durée = définitif).")
            return
    reason = rest.strip() or None

    admin = message.from_user
    problem = await _check_target(action, target, admin.id, bot, cfg)
    if problem:
        await message.reply(problem)
        return

    until = int(time.time()) + duration if duration else None
    try:
        await _apply(action, target.id, until, bot, cfg)
    except TelegramAPIError as exc:
        log.warning("%s de %s refusé : %s", action, target.id, exc)
        await message.reply(f"❌ Telegram a refusé : {escape(exc.message)}")
        return

    await db.add_action(action, target.id, admin.id, reason, duration, until)
    log.info("%s %s par %s (durée=%s, raison=%s)", action, target.id, admin.id, duration, reason)

    details = [f"👤 {target.label}"]
    if action in TIMED:
        end = f" (jusqu'au {format_date(until, cfg)})" if until else ""
        details.append(f"⏱ Durée : {format_duration(duration)}{end}")
    if action in PUNISHMENTS:
        details.append(f"📝 Raison : {escape(reason) if reason else 'aucune'}")
    await message.reply(f"<b>{ACTION_LABELS[action]}</b>\n" + "\n".join(details))

    in_group = message.chat.type != ChatType.PRIVATE
    reply = message.reply_to_message if in_group else None
    log_lines = [
        f"#{action.upper()} #id{target.id}",
        *details,
        f"👮 Par : {Target.from_user(admin).label}",
        f"🕒 {format_date(time.time(), cfg)}",
    ]
    if in_group:
        log_lines.append(f"🔗 {message_link(cfg.chat_id, message.message_id)}")
    if reply:
        log_lines.append("⬇️ Message visé :")
    await send_log(bot, cfg, "\n".join(log_lines), evidence=(cfg.chat_id, reply.message_id) if reply else None)
