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
from ..flocko_image import Entry, render_board
from ..jokes import flocko_comment
from ..targets import Target
from ..utils import PREFIXES, format_duration, on_cooldown

log = logging.getLogger(__name__)

router = Router(name="flocko")

ROLL_EVERY = 12 * 3600
PER_PAGE = 10
AVATAR_TTL = 6 * 3600
FOOTER = "/flocko : nouveau tirage toutes les 12 h  ·  le meilleur score de chacun compte"

_avatars: dict[int, tuple[float, bytes | None]] = {}


@router.message(Command("flocko", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_flocko(message: Message, db: Database) -> None:
    user = message.from_user
    who = Target.from_user(user).mention
    row = await db.get_flocko(user.id)
    now = int(time.time())

    if row and now - row["last_at"] < ROLL_EVERY:
        remaining = format_duration(ROLL_EVERY - (now - row["last_at"]))
        rank = await db.flocko_rank(user.id)
        await message.reply(
            f"⏳ {who}, ton flocko du moment : <b>{row['last']} %</b>.\n"
            f"Prochain tirage dans {remaining}. La science prend son temps.\n"
            f"🏅 Ton record : {row['best']} % (#{rank} au <code>/topflocko</code>)"
        )
        return

    value = random.randint(0, 100)
    previous_best = row["best"] if row else -1
    row = await db.save_flocko(user.id, value)
    rank = await db.flocko_rank(user.id)
    players = await db.flocko_players()
    record = " — 🎉 <b>NOUVEAU RECORD !</b>" if value > previous_best and previous_best >= 0 else ""
    await message.reply(
        f"🧪 <b>Taux de flocko de {who}</b> : <b>{value} %</b>\n"
        f"{flocko_comment(value)}\n\n"
        f"🏅 Record : {row['best']} % — #{rank} sur {players}{record}\n"
        "⏳ Prochain tirage dans 12 h."
    )


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


async def _board(page: int, bot: Bot, db: Database, cfg: Config) -> tuple[bytes, str, int] | None:
    players = await db.flocko_players()
    if not players:
        return None
    pages = math.ceil(players / PER_PAGE)
    page = max(1, min(page, pages))
    rows = await db.flocko_board((page - 1) * PER_PAGE, PER_PAGE)
    avatars = await asyncio.gather(*(_avatar(bot, row["user_id"]) for row in rows))
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
    png = await asyncio.to_thread(render_board, entries, page, pages, players, FOOTER)
    caption = (
        f"🏆 <b>Top flocko</b> — page {page}/{pages}\n"
        "<i>Le meilleur score de chacun, depuis toujours. <code>/flocko</code> pour tenter ta chance.</i>"
    )
    return png, caption, pages


@router.message(Command("topflocko", "flockotop", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_topflocko(message: Message, bot: Bot, db: Database, cfg: Config) -> None:
    if on_cooldown(f"topflocko:{message.chat.id}", 5):
        return
    board = await _board(1, bot, db, cfg)
    if board is None:
        await message.reply("🏆 Personne n'a encore joué. Lance <code>/flocko</code> et deviens une légende.")
        return
    png, caption, pages = board
    await message.reply_photo(
        BufferedInputFile(png, "topflocko.png"), caption=caption, reply_markup=_keyboard(1, pages)
    )


@router.callback_query(F.data.startswith("flocko:"))
async def on_page(callback: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    target = callback.data.removeprefix("flocko:")
    if not target.isdigit() or not isinstance(callback.message, Message):
        await callback.answer()
        return
    if on_cooldown(f"flockopage:{callback.message.message_id}", 1.5):
        await callback.answer("Doucement, l'imprimante chauffe. 🖨")
        return
    board = await _board(int(target), bot, db, cfg)
    if board is None:
        await callback.answer()
        return
    png, caption, pages = board
    page = max(1, min(int(target), pages))
    try:
        await callback.message.edit_media(
            InputMediaPhoto(media=BufferedInputFile(png, f"topflocko-{page}.png"), caption=caption),
            reply_markup=_keyboard(page, pages),
        )
    except TelegramBadRequest as exc:
        if "not modified" not in exc.message:
            raise
    await callback.answer()
