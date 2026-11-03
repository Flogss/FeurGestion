import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from .config import Config
from .db import Database

log = logging.getLogger(__name__)


class TrackerMiddleware(BaseMiddleware):
    """Mémorise toutes les personnes vues dans le groupe (pseudo -> ID, activité, anciens noms)."""

    def __init__(self, db: Database, cfg: Config) -> None:
        self.db = db
        self.cfg = cfg

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if event.chat.id == self.cfg.chat_id:
            try:
                await self._track(event)
            except Exception:
                log.exception("Échec de l'enregistrement d'un utilisateur")
        return await handler(event, data)

    async def _track(self, message: Message) -> None:
        if message.from_user and not message.sender_chat:
            is_service = bool(message.new_chat_members or message.left_chat_member)
            await self.db.track_user(message.from_user, active=not is_service)

        reply = message.reply_to_message
        if reply and reply.from_user and not reply.sender_chat:
            await self.db.track_user(reply.from_user, active=False)

        for entity in message.entities or message.caption_entities or []:
            if entity.user:
                await self.db.track_user(entity.user, active=False)

        for user in message.new_chat_members or []:
            await self.db.track_user(user, active=False)
