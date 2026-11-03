"""Outils : signalement, ménage (purge / del), épingles, ID, ping."""

import logging
import time

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..filters import IsAdmin, IsMember
from ..targets import Target
from ..utils import PREFIXES, delete_later, format_date, message_link, on_cooldown, send_log

log = logging.getLogger(__name__)

router = Router(name="tools")

PURGE_MAX = 1000


async def report(message: Message, bot: Bot, cfg: Config) -> None:
    """Prévient les admins en privé, avec le message signalé en preuve."""
    reply = message.reply_to_message
    if message.chat.id != cfg.chat_id:
        return
    if reply is None:
        await message.reply("🚨 Réponds au message à signaler. Je suis un bot, pas un médium.")
        return
    if on_cooldown(f"report:{message.from_user.id}", 60):
        return
    lines = [
        f"#REPORT #id{reply.from_user.id if reply.from_user else 0}",
        "<b>🚨 Signalement</b>",
        f"👤 Signalé : {Target.from_user(reply.from_user).label}" if reply.from_user else "👤 Signalé : inconnu",
        f"🙋 Par : {Target.from_user(message.from_user).label}",
        f"🕒 {format_date(time.time(), cfg)}",
        f"🔗 {message_link(cfg.chat_id, reply.message_id)}",
        "⬇️ Message signalé :",
    ]
    await send_log(bot, cfg, "\n".join(lines), evidence=(cfg.chat_id, reply.message_id))
    await message.reply("🚨 Signalé aux admins. Ils arrivent… dès qu'ils auront fini leur sieste.")


@router.message(Command("report", "signaler", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_report(message: Message, bot: Bot, cfg: Config) -> None:
    await report(message, bot, cfg)


@router.message(Command("purge", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_purge(message: Message, bot: Bot, cfg: Config) -> None:
    reply = message.reply_to_message
    if message.chat.type == ChatType.PRIVATE or reply is None:
        await message.reply("🧹 Réponds au premier message à effacer : je supprime tout jusqu'à ta commande.")
        return
    first = max(reply.message_id, message.message_id - PURGE_MAX + 1)
    ids = list(range(first, message.message_id + 1))
    for start in range(0, len(ids), 100):
        try:
            await bot.delete_messages(message.chat.id, ids[start : start + 100])
        except TelegramAPIError as exc:
            log.warning("Purge partielle : %s", exc)
    log.info("Purge de %s messages par %s", len(ids), message.from_user.id)
    notice = await bot.send_message(
        message.chat.id, f"🧹 {len(ids) - 1} messages balayés. Le ménage est fait, ça fera 15 € de l'heure."
    )
    delete_later(bot, notice.chat.id, notice.message_id, 8)


@router.message(Command("del", "suppr", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_del(message: Message, bot: Bot) -> None:
    reply = message.reply_to_message
    if message.chat.type == ChatType.PRIVATE or reply is None:
        await message.reply("🗑 Réponds au message à supprimer.")
        return
    try:
        await bot.delete_messages(message.chat.id, [reply.message_id, message.message_id])
    except TelegramAPIError as exc:
        await message.reply(f"❌ Impossible : {exc.message}")


@router.message(Command("pin", "epingle", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_pin(message: Message, command: CommandObject, bot: Bot) -> None:
    reply = message.reply_to_message
    if message.chat.type == ChatType.PRIVATE or reply is None:
        await message.reply("📌 Réponds au message à épingler. (<code>.pin silence</code> pour ne pas notifier)")
        return
    silent = (command.args or "").strip().lower() in ("silence", "silent", "chut")
    try:
        await bot.pin_chat_message(message.chat.id, reply.message_id, disable_notification=silent)
    except TelegramAPIError as exc:
        await message.reply(f"❌ Impossible : {exc.message}")
        return
    await message.reply("📌 Épinglé. Lisez-le, sinon à quoi bon. (feur)")


@router.message(Command("unpin", "desepingle", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_unpin(message: Message, bot: Bot) -> None:
    reply = message.reply_to_message
    try:
        await bot.unpin_chat_message(message.chat.id, message_id=reply.message_id if reply else None)
    except TelegramAPIError as exc:
        await message.reply(f"❌ Impossible : {exc.message}")
        return
    await message.reply("📍 Désépinglé. Retour à l'anonymat.")


@router.message(Command("id", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_id(message: Message) -> None:
    reply = message.reply_to_message
    lines = []
    if reply and reply.from_user:
        lines.append(f"🆔 {Target.from_user(reply.from_user).mention} : <code>{reply.from_user.id}</code>")
    lines.append(f"🆔 Toi : <code>{message.from_user.id}</code>")
    if message.chat.type != ChatType.PRIVATE:
        lines.append(f"🆔 Ce groupe : <code>{message.chat.id}</code>")
    lines.append("<i>Ne le tatoue pas, c'est pas si important.</i>")
    await message.reply("\n".join(lines))


@router.message(Command("ping", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_ping(message: Message) -> None:
    start = time.monotonic()
    sent = await message.reply("🏓 Pong…")
    elapsed = (time.monotonic() - start) * 1000
    await sent.edit_text(f"🏓 Pong ! {elapsed:.0f} ms.\n<i>Et si t'avais dit « quoi », j'aurais dit « feur ».</i>")
