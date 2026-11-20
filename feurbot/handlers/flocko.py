"""/flocko : un pourcentage toutes les 12 h. /topflocko : le classement des records, en image."""

import asyncio
import logging
import math
import random
import time
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from ..config import Config
from ..db import Database, full_name
from ..filters import IsMember
from ..utils import PREFIXES, format_duration, on_cooldown

log = logging.getLogger(__name__)

router = Router(name="flocko")

ROLL_EVERY = 12 * 3600
PER_PAGE = 10
AVATAR_TTL = 24 * 3600
AVATAR_WAIT = 2.0  # au-delà, on dessine l'initiale plutôt que d'attendre la photo

# Image déjà envoyée pour un état donné du classement : on renvoie le même fichier, sans rien recalculer
_sent_boards: dict[tuple, str] = {}

_avatars: dict[int, tuple[float, bytes | None]] = {}


@router.message(Command("flocko", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_flocko(message: Message, db: Database) -> None:
    user_id = message.from_user.id
    row = await db.get_flocko(user_id)
    now = int(time.time())
    if row and now - row["last_at"] < ROLL_EVERY:
        remaining = format_duration(ROLL_EVERY - (now - row["last_at"]))
        await message.reply(f"🧪 <b>{row['last']} %</b> · ⏳ {remaining}")
        return
    value = random.randint(0, 100)
    await db.save_flocko(user_id, value)
    await message.reply(f"🧪 <b>{value} %</b>")


async def _avatar(bot: Bot, user_id: int) -> bytes | None:
    cached = _avatars.get(user_id)
    if cached and time.monotonic() - cached[0] < AVATAR_TTL:
        return cached[1]
    data = None
    try:
        photos = await asyncio.wait_for(bot.get_user_profile_photos(user_id, limit=1), 5)
        if photos.total_count and photos.photos:
            smallest = photos.photos[0][0]
            buffer = await asyncio.wait_for(bot.download(smallest.file_id), 5)
            data = buffer.read() if buffer else None
    except (TelegramAPIError, asyncio.TimeoutError, OSError) as exc:
        log.debug("Photo de profil de %s indisponible : %s", user_id, exc)
    _avatars[user_id] = (time.monotonic(), data)
    return data


def _keyboard(page: int, pages: int) -> InlineKeyboardMarkup | None:
    if pages <= 1:
        return None
    # Comme demandé : flèche de gauche = page suivante, flèche de droite = page précédente
    buttons = []
    if page < pages:
        buttons.append(InlineKeyboardButton(text="⬅️ Suivant", callback_data=f"flocko:{page + 1}"))
    buttons.append(InlineKeyboardButton(text=f"📄 {page}/{pages}", callback_data="flocko:noop"))
    if page > 1:
        buttons.append(InlineKeyboardButton(text="Précédent ➡️", callback_data=f"flocko:{page - 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def _avatars_for(bot: Bot, user_ids: list[int]) -> list[bytes | None]:
    tasks = [asyncio.ensure_future(_avatar(bot, user_id)) for user_id in user_ids]
    await asyncio.wait(tasks, timeout=AVATAR_WAIT)  # les retardataires finissent en fond et rempliront le cache
    return [task.result() if task.done() and not task.exception() else None for task in tasks]


async def _board(page: int, bot: Bot, db: Database, cfg: Config) -> tuple[bytes | str, int, tuple] | None:
    """Image de la page (ou file_id si cette page exacte a déjà été envoyée), nombre de pages, signature."""
    players = await db.flocko_players()
    if not players:
        return None
    pages = math.ceil(players / PER_PAGE)
    page = max(1, min(page, pages))
    rows = await db.flocko_board((page - 1) * PER_PAGE, PER_PAGE)
    signature = (page, pages, players, *((r["user_id"], r["best"], r["first_name"], r["last_name"]) for r in rows))
    if signature in _sent_boards:
        return _sent_boards[signature], pages, signature

    from ..flocko_image import Entry, render_board  # Pillow n'est chargé qu'au premier /topflocko

    avatars = await _avatars_for(bot, [row["user_id"] for row in rows])
    entries = [
        Entry(
            rank=(page - 1) * PER_PAGE + index + 1,
            user_id=row["user_id"],
            name=full_name(row["first_name"], row["last_name"]) if row["first_name"] else str(row["user_id"]),
            value=row["best"],
            date=datetime.fromtimestamp(row["best_at"], cfg.tz).strftime("%d/%m/%Y"),
            avatar=avatar,
        )
        for index, (row, avatar) in enumerate(zip(rows, avatars))
    ]
    image = await asyncio.to_thread(render_board, entries, page, pages, players)
    return image, pages, signature


def _remember(signature: tuple, sent: Message | None) -> None:
    if isinstance(sent, Message) and sent.photo:
        if len(_sent_boards) > 100:
            _sent_boards.clear()
        _sent_boards[signature] = sent.photo[-1].file_id


def _photo(image: bytes | str, page: int) -> BufferedInputFile | str:
    return image if isinstance(image, str) else BufferedInputFile(image, f"topflocko-{page}.jpg")


@router.message(Command("topflocko", "flockotop", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_topflocko(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    if on_cooldown(f"topflocko:{message.chat.id}", 5):
        return
    board = await _board(1, bot, db, cfg)
    if board is None:
        await message.reply("🏆 Personne n'a encore joué.")
        return
    image, pages, signature = board
    sent = await message.reply_photo(_photo(image, 1), reply_markup=_keyboard(1, pages))
    _remember(signature, sent)


@router.callback_query(F.data.startswith("flocko:"))
async def on_page(callback: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    target = callback.data.removeprefix("flocko:")
    if not target.isdigit() or not isinstance(callback.message, Message):
        await callback.answer()
        return
    if on_cooldown(f"flockopage:{callback.message.message_id}", 1.5):
        await callback.answer()
        return
    board = await _board(int(target), bot, db, cfg)
    if board is None:
        await callback.answer()
        return
    image, pages, signature = board
    page = max(1, min(int(target), pages))
    try:
        edited = await callback.message.edit_media(
            InputMediaPhoto(media=_photo(image, page)), reply_markup=_keyboard(page, pages)
        )
        _remember(signature, edited)
    except TelegramBadRequest as exc:
        if "not modified" not in exc.message:
            raise
    await callback.answer()
