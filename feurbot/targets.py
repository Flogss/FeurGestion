from dataclasses import dataclass
from html import escape

from aiogram import Bot
from aiogram.enums import ChatType, MessageEntityType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, User

from .config import Config
from .db import Database, full_name
from .utils import mention


@dataclass
class Target:
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None

    @classmethod
    def from_user(cls, user: User) -> "Target":
        return cls(user.id, user.first_name, user.last_name, user.username)

    @classmethod
    def from_row(cls, row) -> "Target":
        return cls(row["user_id"], row["first_name"], row["last_name"], row["username"])

    @property
    def name(self) -> str:
        return full_name(self.first_name, self.last_name) if self.first_name else f"Utilisateur {self.id}"

    @property
    def mention(self) -> str:
        return mention(self.id, self.name)

    @property
    def label(self) -> str:
        """Mention + ID + pseudo, pour les réponses et les logs."""
        handle = f" @{escape(self.username)}" if self.username else ""
        return f"{self.mention} (<code>{self.id}</code>){handle}"


async def resolve_target(
    message: Message, args: str, bot: Bot, db: Database, cfg: Config
) -> tuple[Target | None, str, str | None]:
    """Trouve la cible d'une commande : @pseudo, ID, mention sans pseudo ou message auquel on répond.

    Retourne (cible, arguments restants, erreur).
    """
    # Mention d'un utilisateur sans @pseudo (lien sur son nom)
    text = message.text or message.caption or ""
    for entity in message.entities or message.caption_entities or []:
        if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
            chunk = entity.extract_from(text)
            if chunk in args:
                return Target.from_user(entity.user), args.replace(chunk, "", 1).strip(), None

    parts = args.split(maxsplit=1)
    first = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if first.startswith("@") and len(first) > 1:
        row = await db.find_by_username(first)
        if row is None:
            return None, rest, (
                f"❌ Je ne connais pas {escape(first)}.\n"
                "Il doit avoir écrit au moins une fois depuis mon arrivée (je suis un bot, pas un voyant). "
                "Sinon utilise son ID ou réponds à un de ses messages."
            )
        return Target.from_row(row), rest, None

    if first.isdigit() and len(first) >= 5:
        user_id = int(first)
        row = await db.get_user(user_id)
        if row:
            return Target.from_row(row), rest, None
        try:
            member = await bot.get_chat_member(cfg.chat_id, user_id)
            return Target.from_user(member.user), rest, None
        except TelegramAPIError:
            return Target(user_id), rest, None

    reply = message.reply_to_message
    if (
        message.chat.type != ChatType.PRIVATE
        and reply
        and reply.from_user
        and not reply.forum_topic_created
        and not reply.sender_chat
    ):
        return Target.from_user(reply.from_user), args, None

    return None, args, None
