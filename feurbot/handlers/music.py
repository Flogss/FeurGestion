"""Recherche de musique « inline » : taper @feurzizibot titre dans n'importe quelle conversation."""

import logging
from html import escape
from urllib.parse import quote, quote_plus

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultAudio,
    InlineQueryResultsButton,
    InputTextMessageContent,
    LinkPreviewOptions,
)

from .. import deezer

log = logging.getLogger(__name__)

router = Router(name="music")

PAGE = 20


def _duration(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _links(track: deezer.Track) -> InlineKeyboardMarkup:
    search = f"{track.artist} {track.title}"
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🎧 Deezer", url=track.link),
            InlineKeyboardButton(text="🟢 Spotify", url=f"https://open.spotify.com/search/{quote(search)}"),
            InlineKeyboardButton(text="▶️ YouTube", url=f"https://www.youtube.com/results?search_query={quote_plus(search)}"),
        ]]
    )


def _caption(track: deezer.Track, with_preview: bool) -> str:
    details = " · ".join(part for part in (escape(track.album), f"⏱ {_duration(track.duration)}") if part)
    footer = "Extrait de 30 s — le morceau complet sur Deezer, Spotify ou YouTube 👇" if with_preview else "Écoute-le ici 👇"
    return f"🎵 <b>{escape(track.title)}</b> — {escape(track.artist)}\n💿 {details}\n<i>{footer}</i>"


def _result(track: deezer.Track):
    if track.preview:
        return InlineQueryResultAudio(
            id=f"dz{track.id}",
            audio_url=track.preview,
            title=track.title,
            performer=track.artist,
            audio_duration=30,
            caption=_caption(track, True),
            parse_mode="HTML",
            reply_markup=_links(track),
        )
    # Pas d'extrait disponible : une carte avec la pochette et les liens
    return InlineQueryResultArticle(
        id=f"dz{track.id}",
        title=track.title,
        description=f"{track.artist} · {track.album} (pas d'extrait)",
        thumbnail_url=track.cover or None,
        input_message_content=InputTextMessageContent(
            message_text=_caption(track, False),
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(url=track.cover or None, prefer_large_media=True),
        ),
        reply_markup=_links(track),
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
