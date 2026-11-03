import logging
import time
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..config import Config
from ..db import Database
from ..filters import IsAdmin
from ..targets import Target, resolve_target
from ..jokes import quip
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
    "unban": ".deban @pseudo|ID",
    "mute": ".mute @pseudo|ID [durée] [raison]",
    "unmute": ".demute @pseudo|ID",
    "kick": ".kick @pseudo|ID [raison]",
}
ALIASES = {"deban": "unban", "demute": "unmute"}
TIMED = ("ban", "mute")
PUNISHMENTS = ("ban", "mute", "kick", "warn")
UNDO = {"ban": "unban", "mute": "unmute"}


def undo_keyboard(action_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Annuler", callback_data=f"undo:{action_id}")]]
    )


async def check_target(action: str, target: Target, admin_id: int, bot: Bot, cfg: Config) -> str | None:
    if target.id == bot.id:
        return "🙃 Me sanctionner, moi ? Je suis intouchable. Comme le « feur » après un « quoi »."
    if action in PUNISHMENTS:
        if target.id == admin_id:
            return "🙃 Te sanctionner toi-même ? Va voir un psy, pas un bot."
        if target.id in cfg.admin_ids:
            return "❌ C'est un admin du bot. Entre collègues, on se respecte."

    try:
        member = await bot.get_chat_member(cfg.chat_id, target.id)
    except TelegramAPIError:
        return None  # Telegram ne le connaît pas dans ce groupe : on tente quand même

    if action in PUNISHMENTS and member.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR):
        return "❌ Impossible, c'est un admin du groupe. Même moi j'ai pas ce pouvoir."
    if action == "kick" and not in_chat(member):
        return "ℹ️ Il n'est même pas dans le groupe. Tu tapes dans le vide."
    if action == "unban" and member.status != ChatMemberStatus.KICKED:
        return "ℹ️ Il n'est pas banni. Le débannir de quoi ? (feur)"
    if action == "unmute" and not (member.status == ChatMemberStatus.RESTRICTED and not member.can_send_messages):
        return "ℹ️ Il n'est pas mute. Il parle déjà assez, laisse-le."
    return None


async def apply_sanction(action: str, user_id: int, until: int | None, bot: Bot, cfg: Config) -> None:
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


@router.message(Command(*USAGE, *ALIASES, prefix=PREFIXES, ignore_case=True))
async def cmd_sanction(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    action = ALIASES.get(command.command.lower(), command.command.lower())
    target, rest, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error:
        await message.reply(error)
        return
    if target is None:
        await message.reply(
            f"Usage : <code>{escape(USAGE[action])}</code>\n"
            "Ou réponds à un message de la personne. Je suis bon, mais pas devin."
        )
        return

    duration = None
    if action in TIMED:
        duration, rest = split_duration(rest)
        if duration is not None and not MIN_DURATION <= duration <= MAX_DURATION:
            await message.reply(
                "❌ La durée doit être entre 30s et 366j (sans durée = définitif). "
                "C'est pas moi qui ai fait les règles, c'est Telegram."
            )
            return
    reason = rest.strip() or None

    admin = message.from_user
    problem = await check_target(action, target, admin.id, bot, cfg)
    if problem:
        await message.reply(problem)
        return

    until = int(time.time()) + duration if duration else None
    try:
        await apply_sanction(action, target.id, until, bot, cfg)
    except TelegramAPIError as exc:
        log.warning("%s de %s refusé : %s", action, target.id, exc)
        await message.reply(f"❌ Telegram a refusé : {escape(exc.message)} (c'est pas moi, c'est lui)")
        return

    action_id = await db.add_action(action, target.id, admin.id, reason, duration, until)
    log.info("%s %s par %s (durée=%s, raison=%s)", action, target.id, admin.id, duration, reason)

    details = [f"👤 {target.label}"]
    if action in TIMED:
        end = f" (jusqu'au {format_date(until, cfg)})" if until else ""
        details.append(f"⏱ Durée : {format_duration(duration)}{end}")
    if action in PUNISHMENTS:
        details.append(f"📝 Raison : {escape(reason) if reason else 'aucune'}")

    in_group = message.chat.type != ChatType.PRIVATE
    reply = message.reply_to_message if in_group else None
    # Au ban / mute, on efface la commande et le message visé (seulement s'il est bien de la personne visée)
    clean_up = action in ("ban", "mute") and in_group
    to_delete = [message.message_id] if clean_up else []
    if clean_up and reply and reply.from_user and reply.from_user.id == target.id:
        to_delete.append(reply.message_id)

    # Le log part avant la suppression : le message visé y est transféré comme preuve
    log_lines = [
        f"#{action.upper()} #id{target.id}",
        *details,
        f"👮 Par : {Target.from_user(admin).label}",
        f"🕒 {format_date(time.time(), cfg)}",
    ]
    if in_group and not clean_up:
        log_lines.append(f"🔗 {message_link(cfg.chat_id, message.message_id)}")
    if reply:
        log_lines.append("⬇️ Message visé :")
    await send_log(bot, cfg, "\n".join(log_lines), evidence=(cfg.chat_id, reply.message_id) if reply else None)

    text = f"<b>{ACTION_LABELS[action]}</b>\n" + "\n".join(details) + f"\n\n<i>{quip(action)}</i>"
    markup = undo_keyboard(action_id) if action in UNDO else None
    if to_delete:
        try:
            await bot.delete_messages(cfg.chat_id, to_delete)
        except TelegramAPIError as exc:
            log.warning("Suppression des messages %s impossible : %s", to_delete, exc)
        await bot.send_message(cfg.chat_id, text, reply_markup=markup)
    else:
        await message.reply(text, reply_markup=markup)


@router.callback_query(F.data.startswith("undo:"))
async def on_undo(callback: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    admin = callback.from_user
    if admin.id not in cfg.admin_ids:
        await callback.answer("⛔️ Pas touche, c'est réservé aux admins.", show_alert=True)
        return

    row = await db.get_action(int(callback.data.removeprefix("undo:")))
    if row is None or row["action"] not in UNDO:
        await callback.answer("❌ Sanction introuvable. Elle s'est sauvée ?", show_alert=True)
        return

    undo = UNDO[row["action"]]
    try:
        await apply_sanction(undo, row["user_id"], None, bot, cfg)
    except TelegramAPIError as exc:
        await callback.answer(f"❌ Telegram a refusé : {exc.message}", show_alert=True)
        return

    await db.add_action(undo, row["user_id"], admin.id, f"annulation du {row['action']} #{row['id']}")
    log.info("%s #%s annulé par %s", row["action"], row["id"], admin.id)
    await callback.answer("✅ Annulé")

    note = f"↩️ <b>Annulé</b> par {Target.from_user(admin).mention}"
    if row["action"] == "ban":
        note += " — il peut revenir avec un lien"
    note += f"\n<i>{quip('undo')}</i>"
    if isinstance(callback.message, Message):
        await callback.message.edit_text(f"{callback.message.html_text}\n\n{note}", reply_markup=None)

    user = await db.get_user(row["user_id"])
    target = Target.from_row(user) if user else Target(row["user_id"])
    await send_log(
        bot,
        cfg,
        f"#{undo.upper()} #id{target.id}\n"
        f"<b>{ACTION_LABELS[undo]}</b> (annulation du {row['action']} du {format_date(row['created_at'], cfg)})\n"
        f"👤 {target.label}\n"
        f"👮 Par : {Target.from_user(admin).label}\n"
        f"🕒 {format_date(time.time(), cfg)}",
    )
