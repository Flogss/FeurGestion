"""Recherche de musique « inline » : taper @feurzizibot titre dans n'importe quelle conversation.

La liste montre les pochettes. Le morceau choisi part d'abord comme une carte avec la pochette, puis le bot
la remplace par l'extrait de 30 s, pochette intégrée au lecteur (automatique si le « inline feedback » est
activé dans @BotFather, sinon avec le bouton ▶️).
"""

import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ChosenInlineResult,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputMediaAudio,
    InputTextMessageContent,
    LinkPreviewOptions,
)

from .. import deezer
from ..config import Config
from ..db import Database

log = logging.getLogger(__name__)

router = Router(name="music")

PAGE = 20
_locks: dict[int, asyncio.Lock] = {}


def _caption(track: deezer.Track) -> str:
    return f"🎵 <b>{escape(track.title)}</b> — {escape(track.artist)}"


def _result(track: deezer.Track) -> InlineQueryResultArticle:
    play = (
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="▶️ Écouter l'extrait", callback_data=f"play:{track.id}")]]
        )
        if track.preview
        else None
    )
    return InlineQueryResultArticle(
        id=f"dz{track.id}",
        title=track.title,
        description=track.artist,
        thumbnail_url=track.cover or None,
        thumbnail_width=250 if track.cover else None,
        thumbnail_height=250 if track.cover else None,
        input_message_content=InputTextMessageContent(
            message_text=_caption(track),
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(
                url=track.cover_big or None, prefer_large_media=True, show_above_text=True
            ),
        ),
        reply_markup=play,
    )


@router.inline_query()
async def on_inline(query: InlineQuery) -> None:
    text = query.query.strip()
    offset = int(query.offset) if query.offset.isdigit() else 0
    try:
        tracks, more = await (deezer.search(text, offset, PAGE) if text else deezer.top_france(offset, PAGE))
    except deezer.DeezerError as exc:
        log.warning("Recherche Deezer « %s » impossible : %s", text, exc)
        await query.answer(
            [], cache_time=5,
            button=InlineQueryResultsButton(text="😵 Deezer fait la sieste, réessaie dans un instant", start_parameter="musique"),
        )
        return

    button = None
    if offset == 0 and not text:
        button = InlineQueryResultsButton(text="🔥 Top France — tape un titre ou un artiste", start_parameter="musique")
    elif offset == 0 and not tracks:
        button = InlineQueryResultsButton(text=f"😶 Rien pour « {text[:40]} ». Même pas un feur.", start_parameter="musique")

    await query.answer(
        [_result(track) for track in tracks],
        cache_time=300,
        is_personal=False,
        next_offset=str(offset + PAGE) if more else "",
        button=button,
    )


async def _audio_file(track: deezer.Track, bot: Bot, db: Database, cfg: Config) -> str:
    """file_id de l'extrait avec sa pochette. Le premier envoi passe en silence par la conversation privée
    de l'admin (message effacé tout de suite) ; ensuite le fichier est réutilisé directement."""
    cached = await db.get_deezer_audio(track.id)
    if cached:
        return cached
    async with _locks.setdefault(track.id, asyncio.Lock()):
        cached = await db.get_deezer_audio(track.id)
        if cached:
            return cached
        audio = await deezer.download(track.preview)
        cover = await deezer.download(track.cover, 200_000) if track.cover else None
        sent = await bot.send_audio(
            cfg.log_chat_id or min(cfg.admin_ids),
            BufferedInputFile(audio, f"{track.artist} - {track.title}.mp3"),
            title=track.title,
            performer=track.artist,
            duration=30,
            thumbnail=BufferedInputFile(cover, "cover.jpg") if cover else None,
            disable_notification=True,
        )
        try:
            await sent.delete()
        except TelegramAPIError:
            pass
        await db.set_deezer_audio(track.id, sent.audio.file_id)
        return sent.audio.file_id


async def _play(inline_message_id: str, track_id: int, bot: Bot, db: Database, cfg: Config) -> bool:
    """Remplace la carte par l'extrait audio. False si ce morceau n'a pas d'extrait."""
    track = await deezer.track(track_id)
    if not track.preview:
        return False
    try:
        media = await _audio_file(track, bot, db, cfg)
    except (deezer.DeezerError, TelegramAPIError) as exc:
        log.warning("Extrait avec pochette impossible pour %s : %s", track_id, exc)
        media = track.preview  # sans pochette dans le lecteur, mais ça joue quand même
    await bot.edit_message_media(
        inline_message_id=inline_message_id,
        media=InputMediaAudio(
            media=media, caption=_caption(track), parse_mode="HTML",
            title=track.title, performer=track.artist, duration=30,
        ),
        reply_markup=None,
    )
    return True


@router.chosen_inline_result(F.result_id.startswith("dz"))
async def on_chosen(result: ChosenInlineResult, bot: Bot, db: Database, cfg: Config) -> None:
    if not result.inline_message_id:
        return
    try:
        await _play(result.inline_message_id, int(result.result_id[2:]), bot, db, cfg)
    except (deezer.DeezerError, TelegramAPIError) as exc:
        log.info("Extrait non posé automatiquement (%s) : le bouton ▶️ reste", exc)


@router.callback_query(F.data.startswith("play:"))
async def on_play(callback: CallbackQuery, bot: Bot, db: Database, cfg: Config) -> None:
    if not callback.inline_message_id:
        await callback.answer()
        return
    try:
        played = await _play(callback.inline_message_id, int(callback.data.removeprefix("play:")), bot, db, cfg)
    except TelegramBadRequest as exc:
        if "not modified" in exc.message:
            await callback.answer()
            return
        await callback.answer("😵 Extrait indisponible pour le moment, réessaie.", show_alert=True)
        return
    except (deezer.DeezerError, TelegramAPIError):
        await callback.answer("😵 Extrait indisponible pour le moment, réessaie.", show_alert=True)
        return
    await callback.answer("▶️ C'est parti !" if played else "Pas d'extrait pour ce morceau, désolé.")
