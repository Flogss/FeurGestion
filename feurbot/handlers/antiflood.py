"""Anti-flood : coupe les rafales de messages et les copier-coller en boucle, sans gêner une vraie conversation.

- rafale : trop de messages en quelques secondes (8 en 6 s en mode « normal ») ;
- répétition : le même message plusieurs fois en une minute ;
- un album photo ou des messages transférés ensemble comptent pour un seul ;
- admins et modos ne sont jamais concernés ;
- sanction progressive sur 24 h : 1 min, puis 10 min, puis 1 h de mute. Les messages du flood sont effacés.
"""

import logging
import time
from collections import deque
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Config
from ..db import Database
from ..filters import IsAdmin
from ..targets import Target
from ..utils import PREFIXES, format_date, format_duration, group_admin_ids, send_log
from .moderation import apply_sanction, undo_keyboard

log = logging.getLogger(__name__)

router = Router(name="antiflood")

# mode -> (messages max, en combien de secondes, répétitions max du même message en 60 s)
MODES = {
    "doux": (10, 6, 5),
    "normal": (8, 6, 4),
    "strict": (6, 6, 3),
}
DEFAULT_MODE = "normal"
REPEAT_WINDOW = 60
LADDER = (60, 600, 3600)  # 1re, 2e, 3e fois (et plus) sur 24 h
STRIKE_MEMORY = 24 * 3600

_recent: dict[int, deque] = {}  # user_id -> (instant, message_id, clé du contenu)
_strikes: dict[int, list[float]] = {}  # user_id -> instants des sanctions anti-flood
_muted_until: dict[int, float] = {}  # pendant que le mute se met en place, on efface ce qui arrive encore
_last_cleanup = 0.0


def _key(message: Message) -> str:
    """Ce qui identifie le contenu, pour repérer les copier-coller (texte, sticker, même photo...)."""
    text = message.text or message.caption
    if text:
        return " ".join(text.lower().split())
    for kind in ("sticker", "animation", "photo", "video", "voice", "video_note", "document", "audio"):
        media = getattr(message, kind)
        if media:
            media = media[-1] if isinstance(media, list) else media
            return f"{kind}:{media.file_unique_id}"
    return ""


def _cleanup(now: float) -> None:
    global _last_cleanup
    if now - _last_cleanup < 300:
        return
    _last_cleanup = now
    for user_id in [uid for uid, history in _recent.items() if not history or now - history[-1][0] > REPEAT_WINDOW]:
        del _recent[user_id]
    for user_id in list(_strikes):
        _strikes[user_id] = [at for at in _strikes[user_id] if now - at < STRIKE_MEMORY]
        if not _strikes[user_id]:
            del _strikes[user_id]


async def get_mode(db: Database) -> str:
    return await db.get_setting("antiflood", DEFAULT_MODE)


async def check(message: Message, bot: Bot, db: Database, cfg: Config) -> bool:
    """Appelé pour chaque message du groupe. Retourne True si c'était du flood (message supprimé)."""
    user = message.from_user
    now = time.monotonic()
    if _muted_until.get(user.id, 0) > now:
        try:
            await message.delete()
        except TelegramAPIError:
            pass
        return True

    mode = await get_mode(db)
    if mode not in MODES or user.is_bot:
        return False
    max_messages, window, max_repeats = MODES[mode]
    _cleanup(now)

    history = _recent.setdefault(user.id, deque())
    # Album photo ou transfert groupé : Telegram envoie N messages d'un coup, on en compte un seul
    group = message.media_group_id or (f"fwd:{message.date.timestamp()}" if message.forward_origin else None)
    if group and history and history[-1][3] == group:
        return False
    key = _key(message)
    history.append((now, message.message_id, key, group))
    while history and now - history[0][0] > max(window, REPEAT_WINDOW):
        history.popleft()

    burst = [entry for entry in history if now - entry[0] <= window]
    repeats = [entry for entry in history if key and entry[2] == key]
    if len(burst) < max_messages and len(repeats) < max_repeats:
        return False

    # C'est du flood... sauf pour l'équipe (vérifié seulement maintenant : c'est rare et ça évite des appels)
    if user.id in await group_admin_ids(bot, cfg) or await db.is_mod(user.id):
        history.clear()
        return False

    flooded = burst if len(burst) >= max_messages else repeats
    message_ids = sorted({entry[1] for entry in flooded} | {message.message_id})
    history.clear()
    await _punish(message, message_ids, "rafale" if flooded is burst else "copier-coller", bot, db, cfg)
    return True


async def _punish(message: Message, message_ids: list[int], kind: str, bot: Bot, db: Database, cfg: Config) -> None:
    user = message.from_user
    now = time.monotonic()
    strikes = [at for at in _strikes.get(user.id, []) if now - at < STRIKE_MEMORY]
    duration = LADDER[min(len(strikes), len(LADDER) - 1)]
    _strikes[user.id] = [*strikes, now]
    _muted_until[user.id] = now + 10

    until = int(time.time()) + duration
    try:
        await apply_sanction("mute", user.id, until, bot, cfg)
    except TelegramAPIError as exc:
        log.warning("Mute anti-flood impossible pour %s : %s", user.id, exc)
        return
    try:
        await bot.delete_messages(message.chat.id, message_ids)
    except TelegramAPIError as exc:
        log.warning("Messages du flood non supprimés : %s", exc)

    reason = f"anti-flood ({kind})"
    action_id = await db.add_action("mute", user.id, None, reason, duration, until)
    target = Target.from_user(user)
    log.info("Flood de %s (%s, %s messages) : mute %s", user.id, kind, len(message_ids), duration)
    await bot.send_message(
        message.chat.id,
        f"🌊 {target.mention} : flood → 🔇 {format_duration(duration)}",
        reply_markup=undo_keyboard(action_id),
    )
    await send_log(
        bot,
        cfg,
        f"#FLOOD #id{user.id}\n👤 {target.label}\n🌊 {kind} · {len(message_ids)} messages effacés\n"
        f"⏱ {format_duration(duration)} (jusqu'au {format_date(until, cfg)})",
    )


@router.message(Command("antiflood", "flood", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_antiflood(message: Message, command: CommandObject, db: Database) -> None:
    arg = (command.args or "").strip().lower()
    if arg in (*MODES, "off"):
        await db.set_setting("antiflood", arg)
        await message.reply("🌊 Anti-flood désactivé" if arg == "off" else f"🌊 Anti-flood : <b>{arg}</b>")
        return
    mode = await get_mode(db)
    if mode in MODES:
        max_messages, window, max_repeats = MODES[mode]
        state = f"<b>{escape(mode)}</b> — {max_messages} messages en {window} s, ou {max_repeats} fois le même"
    else:
        state = "<b>désactivé</b>"
    await message.reply(f"🌊 Anti-flood : {state}\n<code>/antiflood doux|normal|strict|off</code>")
