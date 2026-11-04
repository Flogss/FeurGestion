from aiogram.enums import ChatType
from aiogram.filters import Filter
from aiogram.types import ChatMemberUpdated, Message

from .config import Config
from .db import Database


class IsAdmin(Filter):
    """Admin du bot (ADMIN_IDS), dans le groupe géré ou en message privé avec le bot."""

    async def __call__(self, message: Message, cfg: Config) -> bool:
        if not message.from_user or message.from_user.id not in cfg.admin_ids:
            return False
        return message.chat.id == cfg.chat_id or message.chat.type == ChatType.PRIVATE


async def is_staff(user_id: int, cfg: Config, db: Database) -> bool:
    """Admin du bot ou modo."""
    return user_id in cfg.admin_ids or await db.is_mod(user_id)


class IsStaff(Filter):
    """Admin du bot ou modo nommé avec .mod, dans le groupe géré ou en privé avec le bot."""

    async def __call__(self, message: Message, cfg: Config, db: Database) -> bool:
        if not message.from_user or not await is_staff(message.from_user.id, cfg, db):
            return False
        return message.chat.id == cfg.chat_id or message.chat.type == ChatType.PRIVATE


class IsMember(Filter):
    """N'importe qui, dans le groupe géré ou en privé avec le bot (commandes publiques)."""

    async def __call__(self, message: Message, cfg: Config) -> bool:
        return message.chat.id == cfg.chat_id or message.chat.type == ChatType.PRIVATE


class InManagedChat(Filter):
    async def __call__(self, event: ChatMemberUpdated, cfg: Config) -> bool:
        return event.chat.id == cfg.chat_id


class IsAnonymousAdmin(Filter):
    """Admin du groupe qui écrit en mode anonyme : impossible de savoir qui c'est."""

    async def __call__(self, message: Message, cfg: Config) -> bool:
        return message.chat.id == cfg.chat_id and bool(
            message.sender_chat and message.sender_chat.id == message.chat.id
        )
