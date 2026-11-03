import logging
from collections.abc import Awaitable, Callable
from html import escape
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message

from .config import Config
from .db import Database, full_name
from .handlers import afk, locks
from .targets import Target

log = logging.getLogger(__name__)

Handler = Callable[[Message, dict[str, Any]], Awaitable[Any]]


class TrackerMiddleware(BaseMiddleware):
    """Mémorise toutes les personnes vues dans le groupe (pseudo -> ID, activité, anciens noms)."""

    def __init__(self, db: Database, cfg: Config) -> None:
        self.db = db
        self.cfg = cfg

    async def __call__(self, handler: Handler, event: Message, data: dict[str, Any]) -> Any:
        if event.chat.id == self.cfg.chat_id:
            try:
                await self._track(event, data["bot"])
            except Exception:
                log.exception("Échec de l'enregistrement d'un utilisateur")
        return await handler(event, data)

    async def _track(self, message: Message, bot: Bot) -> None:
        if message.from_user and not message.sender_chat:
            is_service = bool(message.new_chat_members or message.left_chat_member)
            change = await self.db.track_user(message.from_user, active=not is_service)
            if change and await self.db.get_setting("sangmata", False):
                await self._announce(message, change, bot)

        reply = message.reply_to_message
        if reply and reply.from_user and not reply.sender_chat:
            await self.db.track_user(reply.from_user, active=False)

        for entity in message.entities or message.caption_entities or []:
            if entity.user:
                await self.db.track_user(entity.user, active=False)

        for user in message.new_chat_members or []:
            await self.db.track_user(user, active=False)

    async def _announce(self, message: Message, change: tuple[str | None, str], bot: Bot) -> None:
        user = message.from_user
        old_username, old_name = change
        lines = [f"🕵️ <b>Changement d'identité repéré</b> — {Target.from_user(user).mention}"]
        if old_username != user.username:
            before = f"@{escape(old_username)}" if old_username else "sans pseudo"
            after = f"@{escape(user.username)}" if user.username else "sans pseudo"
            lines.append(f"Pseudo : {before} → {after}")
        new_name = full_name(user.first_name, user.last_name)
        if old_name != new_name:
            lines.append(f"Nom : {escape(old_name)} → {escape(new_name)}")
        lines.append("<i>Nouvelle identité, même personne. On t'a vu 👀</i>")
        await bot.send_message(message.chat.id, "\n".join(lines))


class GuardMiddleware(BaseMiddleware):
    """Avant tout le reste : verrous (liens, transferts) puis AFK."""

    def __init__(self, db: Database, cfg: Config) -> None:
        self.db = db
        self.cfg = cfg

    async def __call__(self, handler: Handler, event: Message, data: dict[str, Any]) -> Any:
        if event.chat.id == self.cfg.chat_id and event.from_user and not event.sender_chat:
            bot = data["bot"]
            try:
                if await locks.enforce(event, bot, self.db, self.cfg):
                    return None  # message supprimé : on ne va pas plus loin
                await afk.check(event, bot, self.db, self.cfg)
            except Exception:
                log.exception("Échec des vérifications verrous / AFK")
        return await handler(event, data)
