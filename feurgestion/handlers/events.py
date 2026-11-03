import logging
import time
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatMemberUpdated

from ..config import Config
from ..db import Database, full_name
from ..filters import InManagedChat
from ..targets import Target
from ..utils import ACTION_LABELS, format_date, format_duration, in_chat, send_log
from .welcome import greet

log = logging.getLogger(__name__)

router = Router(name="events")


def _muted(member) -> bool:
    return member.status == ChatMemberStatus.RESTRICTED and not member.can_send_messages


def _until(member) -> int | None:
    until = getattr(member, "until_date", None)
    return int(until.timestamp()) if until and until.timestamp() > 0 else None


@router.chat_member(InManagedChat())
async def on_member_update(event: ChatMemberUpdated, bot: Bot, db: Database, cfg: Config) -> None:
    old, new = event.old_chat_member, event.new_chat_member
    user, actor = new.user, event.from_user
    await db.track_user(user, active=False)

    if not in_chat(old) and in_chat(new):
        if event.invite_link:
            via = f"via le lien {event.invite_link.name or event.invite_link.invite_link}"
        elif actor.id != user.id:
            via = f"ajouté par {full_name(actor.first_name, actor.last_name)}"
        else:
            via = None
        await db.add_action("join", user.id, actor.id if actor.id != user.id else None, via)
        log.info("Arrivée de %s (%s)", user.id, via)
        if not user.is_bot:
            try:
                await greet(user, bot, db, cfg)
            except TelegramAPIError as exc:
                log.warning("Message de bienvenue impossible : %s", exc)
        return

    if actor.id == bot.id:
        return  # Nos propres sanctions sont déjà dans le journal

    if new.status == ChatMemberStatus.KICKED and old.status != ChatMemberStatus.KICKED:
        action = "ban"
    elif old.status == ChatMemberStatus.KICKED and new.status != ChatMemberStatus.KICKED:
        action = "unban"
    elif in_chat(old) and not in_chat(new):
        action = "leave" if actor.id == user.id else "kick"
    elif _muted(new) and not _muted(old):
        action = "mute"
    elif _muted(old) and not _muted(new):
        action = "unmute"
    else:
        return

    until = _until(new) if action in ("ban", "mute") else None
    duration = until - int(time.time()) if until else None
    admin_id = actor.id if actor.id != user.id else None
    await db.add_action(action, user.id, admin_id, None, duration, until)
    log.info("%s %s par %s (hors bot)", action, user.id, actor.id)

    if action == "leave":
        return
    # Sanction faite à la main par un admin (pas via le bot) : on la note aussi
    lines = [f"#{action.upper()} #id{user.id} <i>(fait à la main)</i>", f"<b>{ACTION_LABELS[action]}</b>"]
    lines.append(f"👤 {Target.from_user(user).label}")
    if action in ("ban", "mute"):
        end = f" (jusqu'au {format_date(until, cfg)})" if until else ""
        lines.append(f"⏱ Durée : {format_duration(duration)}{end}")
    lines.append(f"👮 Par : {Target.from_user(actor).label}")
    lines.append(f"🕒 {format_date(time.time(), cfg)}")
    await send_log(bot, cfg, "\n".join(lines))


@router.my_chat_member(InManagedChat())
async def on_bot_status(event: ChatMemberUpdated, bot: Bot, cfg: Config) -> None:
    new = event.new_chat_member
    if new.status == ChatMemberStatus.ADMINISTRATOR:
        text = "✅ Je suis admin du groupe."
        if not new.can_restrict_members:
            text += "\n⚠️ Il me manque le droit « Bannir des utilisateurs » : ban/mute impossibles."
    elif in_chat(new):
        text = "⚠️ Je ne suis plus admin du groupe : ban/mute impossibles et je ne vois plus les commandes."
    else:
        text = "❌ J'ai été retiré du groupe."
    log.info("Statut du bot dans le groupe : %s", new.status)
    await send_log(bot, cfg, f"{text}\n👮 Par : {Target.from_user(event.from_user).label}")


async def check_bot_rights(bot: Bot, cfg: Config) -> None:
    """Au démarrage : prévient l'admin si le bot ne peut pas modérer."""
    try:
        member = await bot.get_chat_member(cfg.chat_id, bot.id)
    except TelegramAPIError as exc:
        log.error("Groupe %s inaccessible : %s", cfg.chat_id, exc)
        await send_log(bot, cfg, f"❌ Je n'arrive pas à accéder au groupe <code>{cfg.chat_id}</code> : {escape(exc.message)}")
        return
    if member.status == ChatMemberStatus.ADMINISTRATOR and member.can_restrict_members:
        log.info("Droits OK dans le groupe %s", cfg.chat_id)
        return
    log.warning("Le bot n'est pas admin avec le droit de bannir (statut : %s)", member.status)
    await send_log(
        bot,
        cfg,
        "⚠️ Je ne suis pas admin du groupe avec le droit « Bannir des utilisateurs ».\n"
        "Tant que ce n'est pas fait, je ne vois pas les commandes <code>.ban</code>, <code>.mute</code>… "
        "et je ne peux sanctionner personne.",
    )
