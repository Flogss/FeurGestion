import logging
import re
from datetime import datetime
from html import escape

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

from .config import Config

log = logging.getLogger(__name__)

# Préfixes acceptés pour les commandes : .ban, !ban, /ban
PREFIXES = ".!/"

ACTION_LABELS = {
    "ban": "🔨 Ban",
    "unban": "♻️ Unban",
    "mute": "🔇 Mute",
    "unmute": "🔊 Unmute",
    "kick": "👢 Kick",
    "join": "📥 Arrivée",
    "leave": "📤 Départ",
}


def in_chat(member) -> bool:
    """La personne fait-elle partie du groupe (même restreinte) ?"""
    if member.status == ChatMemberStatus.RESTRICTED:
        return bool(member.is_member)
    return member.status in (
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    )

MIN_DURATION = 30  # Telegram considère < 30 s comme définitif
MAX_DURATION = 366 * 86400  # et > 366 jours aussi

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "j": 86400, "w": 604800}
_DURATION_RE = re.compile(r"(?:\d+[smhdjw])+", re.IGNORECASE)
_PART_RE = re.compile(r"(\d+)([smhdjw])", re.IGNORECASE)


def parse_duration(token: str) -> int | None:
    """'1m' -> 60, '1h30m' -> 5400, '2d' / '2j' -> 172800. None si ce n'est pas une durée."""
    if not _DURATION_RE.fullmatch(token):
        return None
    return sum(int(n) * _UNITS[unit.lower()] for n, unit in _PART_RE.findall(token))


def split_duration(args: str) -> tuple[int | None, str]:
    parts = args.split(maxsplit=1)
    if parts:
        seconds = parse_duration(parts[0])
        if seconds is not None:
            return seconds, parts[1] if len(parts) > 1 else ""
    return None, args


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "définitif"
    out = []
    for label, size in (("sem", 604800), ("j", 86400), ("h", 3600), ("min", 60), ("s", 1)):
        value, seconds = divmod(seconds, size)
        if value:
            out.append(f"{value}{label}")
    return " ".join(out)


def format_date(ts: int | float | datetime | None, cfg: Config) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        ts = ts.timestamp()
    return datetime.fromtimestamp(ts, cfg.tz).strftime("%d/%m/%Y %H:%M")


def shorten(text: str | None, size: int = 80) -> str:
    if not text:
        return ""
    return text if len(text) <= size else text[: size - 1] + "…"


def chunk_lines(lines: list[str], limit: int = 4000) -> list[str]:
    """Regroupe des lignes en messages de moins de `limit` caractères (Telegram : 4096 max)."""
    chunks, current = [], ""
    for line in lines:
        if current and len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{escape(name)}</a>'


def message_link(chat_id: int, message_id: int) -> str:
    return f"https://t.me/c/{str(chat_id).removeprefix('-100')}/{message_id}"


async def send_log(bot: Bot, cfg: Config, text: str, evidence: tuple[int, int] | None = None) -> None:
    """Envoie un log dans le chat de logs ; `evidence` = (chat_id, message_id) à transférer comme preuve."""
    if cfg.log_chat_id is None:
        return
    try:
        await bot.send_message(cfg.log_chat_id, text)
        if evidence:
            await bot.forward_message(cfg.log_chat_id, evidence[0], evidence[1])
    except TelegramAPIError as exc:
        # Le plus souvent : l'admin n'a jamais fait /start en privé avec le bot
        log.warning("Impossible d'envoyer le log à %s : %s", cfg.log_chat_id, exc)
