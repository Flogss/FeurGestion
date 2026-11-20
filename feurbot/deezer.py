"""Recherche de musiques via l'API publique de Deezer (gratuite, sans clé)."""

import ssl
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import aiohttp
import certifi

API = "https://api.deezer.com"
TOP_FRANCE = 1109890291  # playlist « Top France » de Deezer, montrée quand rien n'est tapé
CACHE_TTL = 600
CACHE_MAX = 500

_session: aiohttp.ClientSession | None = None
_cache: dict[str, tuple[float, dict]] = {}


class DeezerError(Exception):
    pass


@dataclass
class Track:
    id: int
    title: str
    artist: str
    album: str
    duration: int
    preview: str
    link: str
    cover: str
    cover_big: str


async def _get_session() -> None:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where())),
        )


async def _get(path: str, params: dict) -> dict:
    key = f"{path}?{urlencode(sorted(params.items()))}"
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]
    await _get_session()
    try:
        async with _session.get(API + path, params=params) as response:
            data = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        raise DeezerError(str(exc)) from exc
    if not isinstance(data, dict) or "error" in data:
        raise DeezerError(str(data.get("error") if isinstance(data, dict) else data))

    if len(_cache) >= CACHE_MAX:
        for old in sorted(_cache, key=lambda k: _cache[k][0])[: CACHE_MAX // 5]:
            del _cache[old]
    _cache[key] = (time.monotonic(), data)
    return data


def _track(item: dict) -> Track:
    album = item.get("album") or {}
    return Track(
        id=item["id"],
        title=item.get("title") or "Sans titre",
        artist=(item.get("artist") or {}).get("name") or "Artiste inconnu",
        album=album.get("title") or "",
        duration=item.get("duration") or 0,
        preview=item.get("preview") or "",
        link=item.get("link") or f"https://www.deezer.com/track/{item['id']}",
        cover=album.get("cover_medium") or "",
        cover_big=album.get("cover_big") or album.get("cover_medium") or "",
    )


def _parse(data: dict) -> list[Track]:
    return [
        _track(item)
        for item in data.get("data", [])
        if item.get("type", "track") == "track" and item.get("readable", True)
    ]


async def search(query: str, offset: int = 0, limit: int = 20) -> tuple[list[Track], bool]:
    """Morceaux qui correspondent à `query`, et s'il y a une page suivante."""
    data = await _get("/search", {"q": query, "index": offset, "limit": limit})
    return _parse(data), bool(data.get("next"))


async def top_france(offset: int = 0, limit: int = 20) -> tuple[list[Track], bool]:
    data = await _get(f"/playlist/{TOP_FRANCE}/tracks", {"index": offset, "limit": limit})
    return _parse(data), bool(data.get("next"))


async def track(track_id: int) -> Track:
    return _track(await _get(f"/track/{track_id}", {}))


async def download(url: str, max_bytes: int = 5_000_000) -> bytes:
    """Télécharge un extrait ou une pochette (avec une limite de taille, au cas où)."""
    await _get_session()
    try:
        async with _session.get(url) as response:
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                data += chunk
                if len(data) > max_bytes:
                    raise DeezerError("fichier trop gros")
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise DeezerError(str(exc)) from exc
    return bytes(data)


async def close() -> None:
    if _session and not _session.closed:
        await _session.close()
