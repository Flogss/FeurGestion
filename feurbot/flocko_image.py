"""Image du /topflocko : podium pour le top 3, puis des cartes avec barre de progression."""

import io
import os
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH = 1080
PAD = 48
ROW_HEIGHT = 96
ROW_GAP = 14
PODIUM_HEIGHT = 470

WHITE = (255, 255, 255)
MUTED = (185, 179, 217)
GOLD = (255, 213, 74)
SILVER = (207, 216, 220)
BRONZE = (224, 161, 107)
VIOLET = (108, 92, 231)
MEDALS = {1: GOLD, 2: SILVER, 3: BRONZE}
AVATAR_COLORS = [(255, 107, 129), (255, 159, 67), (46, 213, 115), (30, 144, 255), (165, 94, 234), (255, 71, 87)]

FONTS = {
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ],
}


@dataclass
class Entry:
    rank: int
    user_id: int
    name: str
    value: int
    date: str
    avatar: bytes | None = None


@lru_cache(maxsize=32)
def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS[kind]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _glyph(char: str) -> bytes:
    canvas = Image.new("L", (64, 64))
    ImageDraw.Draw(canvas).text((8, 8), char, font=_font("bold", 30), fill=255)
    return canvas.tobytes()


@lru_cache(maxsize=4096)
def _drawable(char: str) -> bool:
    """La police a-t-elle un vrai dessin pour ce caractère (et pas le carré « inconnu ») ?"""
    return char.isspace() or _glyph(char) != _glyph("\U0010fffd")


def _replacement(char: str) -> str:
    """Lettres stylisées (ᴘᴇᴛɪᴛᴇꜱ ᴄᴀᴘɪᴛᴀʟᴇꜱ, 𝐠𝐫𝐚𝐬...) -> lettre normale quand la police ne les connaît pas."""
    if _drawable(char):
        return char
    plain = unicodedata.normalize("NFKD", char)
    if plain != char and all(_drawable(c) for c in plain):
        return plain
    name = unicodedata.name(char, "")
    if "SMALL CAPITAL" in name or "LETTER" in name:
        letter = name.split()[-1]
        if len(letter) == 1 and letter.isalpha():
            return letter
    return ""


def clean_name(name: str) -> str:
    """Retire les emojis et symboles que la police ne sait pas dessiner (sinon : des carrés)."""
    kept = [
        _replacement(char) for char in name
        if char not in "\u200d\ufe0f" and unicodedata.category(char) not in ("So", "Sk", "Cs", "Co", "Cn", "Cf")
    ]
    return " ".join("".join(kept).split()) or "Anonyme"


def _fit(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: float) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _bar_color(value: int) -> tuple[int, int, int]:
    """Rouge -> orange -> vert selon le score."""
    stops = [(0, (255, 77, 109)), (50, (255, 181, 71)), (100, (43, 214, 123))]
    for (start, c1), (end, c2) in zip(stops, stops[1:]):
        if value <= end:
            ratio = (value - start) / (end - start)
            return tuple(round(a + (b - a) * ratio) for a, b in zip(c1, c2))
    return stops[-1][1]


def _background(height: int) -> Image.Image:
    top, bottom = (26, 11, 61), (8, 22, 58)
    gradient = Image.new("RGB", (1, height))
    for y in range(height):
        ratio = y / max(height - 1, 1)
        gradient.putpixel((0, y), tuple(round(a + (b - a) * ratio) for a, b in zip(top, bottom)))
    image = gradient.resize((WIDTH, height)).convert("RGBA")

    # Halos lumineux flous pour donner du relief
    glow = Image.new("RGBA", (WIDTH, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((-220, -260, 520, 380), fill=(214, 51, 255, 120))
    draw.ellipse((WIDTH - 420, 120, WIDTH + 260, 760), fill=(0, 194, 255, 90))
    draw.ellipse((200, height - 300, 900, height + 300), fill=(255, 77, 109, 60))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(110)))
    return image


def _avatar(entry: Entry, size: int) -> Image.Image:
    picture = None
    if entry.avatar:
        try:
            picture = Image.open(io.BytesIO(entry.avatar)).convert("RGB").resize((size, size), Image.LANCZOS)
        except OSError:
            picture = None
    if picture is None:
        picture = Image.new("RGB", (size, size), AVATAR_COLORS[entry.user_id % len(AVATAR_COLORS)])
        draw = ImageDraw.Draw(picture)
        initial = clean_name(entry.name)[0].upper()
        draw.text((size / 2, size / 2), initial, font=_font("bold", int(size * 0.45)), fill=WHITE, anchor="mm")
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4, size * 4), fill=255)
    rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded.paste(picture, (0, 0), mask.resize((size, size), Image.LANCZOS))
    return rounded


def _paste_avatar(image: Image.Image, entry: Entry, center: tuple[int, int], size: int, ring) -> None:
    x, y = center
    draw = ImageDraw.Draw(image)
    border = max(4, size // 22)
    draw.ellipse((x - size / 2 - border, y - size / 2 - border, x + size / 2 + border, y + size / 2 + border), fill=ring)
    image.alpha_composite(_avatar(entry, size), (round(x - size / 2), round(y - size / 2)))


def _badge(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int, rank: int) -> None:
    color = MEDALS.get(rank, VIOLET)
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline=(20, 12, 45), width=4)
    text_color = (40, 28, 10) if rank in MEDALS else WHITE
    size = int(radius * (1.05 if rank < 100 else 0.8))
    draw.text((x, y + 1), str(rank), font=_font("bold", size), fill=text_color, anchor="mm")


def _header(image: Image.Image, players: int, page: int, pages: int) -> None:
    tag = "RECORDS DE TOUS LES TEMPS"
    tag_font = _font("bold", 22)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    tag_width = ImageDraw.Draw(overlay).textlength(tag, font=tag_font) + 44
    ImageDraw.Draw(overlay).rounded_rectangle(
        ((WIDTH - tag_width) / 2, 46, (WIDTH + tag_width) / 2, 86), radius=20, fill=(255, 213, 74, 38), outline=GOLD, width=2
    )
    image.alpha_composite(overlay)
    draw = ImageDraw.Draw(image)
    draw.text((WIDTH / 2, 67), tag, font=tag_font, fill=GOLD, anchor="mm")
    title_font = _font("bold", 96)
    draw.text((WIDTH / 2 + 4, 158), "TOP FLOCKO", font=title_font, fill=(0, 0, 0, 120), anchor="mm")
    draw.text((WIDTH / 2, 152), "TOP FLOCKO", font=title_font, fill=WHITE, anchor="mm")
    subtitle = f"feurchat  ·  {players} joueur{'s' if players > 1 else ''}  ·  page {page}/{pages}"
    draw.text((WIDTH / 2, 222), subtitle, font=_font("regular", 28), fill=MUTED, anchor="mm")


def _podium(image: Image.Image, entries: list[Entry], top: int) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    # (rang, centre x, taille avatar, décalage vertical, hauteur du socle)
    spots = [(2, WIDTH / 2 - 330, 128, 52, 70), (1, WIDTH / 2, 160, 0, 110), (3, WIDTH / 2 + 330, 128, 72, 50)]
    by_rank = {entry.rank: entry for entry in entries}
    base = top + PODIUM_HEIGHT - 20
    for rank, x, _, _, height in spots:
        if rank in by_rank:
            color = MEDALS[rank]
            odraw.rounded_rectangle((x - 140, base - height, x + 140, base), radius=22, fill=(*color, 70))
            odraw.rounded_rectangle((x - 140, base - height, x + 140, base - height + 8), radius=4, fill=(*color, 200))
    image.alpha_composite(overlay)

    draw = ImageDraw.Draw(image)
    for rank, x, size, offset, height in spots:
        entry = by_rank.get(rank)
        if entry is None:
            continue
        center_y = top + 40 + offset + size / 2
        if rank == 1:
            _crown(draw, (x, top + 22 + offset))
        _paste_avatar(image, entry, (x, center_y), size, MEDALS[rank])
        _badge(draw, (x + size / 2 - 12, center_y + size / 2 - 12), 24, rank)
        name_y = center_y + size / 2 + 34
        name_font = _font("bold", 30 if rank == 1 else 27)
        draw.text((x, name_y), _fit(draw, clean_name(entry.name), name_font, 290), font=name_font, fill=WHITE, anchor="mm")
        draw.text(
            (x, name_y + 50), f"{entry.value} %", font=_font("bold", 54 if rank == 1 else 46),
            fill=_bar_color(entry.value), anchor="mm",
        )
        draw.text((x, base - height / 2), f"#{rank}", font=_font("bold", 34), fill=WHITE, anchor="mm")


def _crown(draw: ImageDraw.ImageDraw, center: tuple[float, float]) -> None:
    x, y = center
    points = [(x - 34, y + 18), (x - 34, y - 8), (x - 17, y + 4), (x, y - 20), (x + 17, y + 4), (x + 34, y - 8), (x + 34, y + 18)]
    draw.polygon(points, fill=GOLD)
    for px in (x - 34, x, x + 34):
        draw.ellipse((px - 6, (y - 8 if px != x else y - 20) - 6, px + 6, (y - 8 if px != x else y - 20) + 6), fill=GOLD)


def _rows(image: Image.Image, entries: list[Entry], top: int) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for index, entry in enumerate(entries):
        y = top + index * (ROW_HEIGHT + ROW_GAP)
        accent = MEDALS.get(entry.rank)
        odraw.rounded_rectangle(
            (PAD, y, WIDTH - PAD, y + ROW_HEIGHT), radius=26,
            fill=(255, 255, 255, 22), outline=(*accent, 160) if accent else (255, 255, 255, 40), width=2,
        )
        bar_left, bar_right = 590, WIDTH - PAD - 150
        bar_y = y + ROW_HEIGHT / 2
        odraw.rounded_rectangle((bar_left, bar_y - 9, bar_right, bar_y + 9), radius=9, fill=(255, 255, 255, 35))
    image.alpha_composite(overlay)

    draw = ImageDraw.Draw(image)
    for index, entry in enumerate(entries):
        y = top + index * (ROW_HEIGHT + ROW_GAP)
        middle = y + ROW_HEIGHT / 2
        _badge(draw, (PAD + 46, middle), 27, entry.rank)
        _paste_avatar(image, entry, (PAD + 130, middle), 62, MEDALS.get(entry.rank, (255, 255, 255)))
        name_font = _font("bold", 31)
        draw.text((PAD + 182, middle - 14), _fit(draw, clean_name(entry.name), name_font, 330), font=name_font, fill=WHITE, anchor="lm")
        draw.text((PAD + 182, middle + 22), f"record du {entry.date}", font=_font("regular", 21), fill=MUTED, anchor="lm")
        bar_left, bar_right = 590, WIDTH - PAD - 150
        fill_right = bar_left + (bar_right - bar_left) * entry.value / 100
        if entry.value:
            draw.rounded_rectangle((bar_left, middle - 9, max(fill_right, bar_left + 18), middle + 9), radius=9, fill=_bar_color(entry.value))
        draw.text((WIDTH - PAD - 28, middle), f"{entry.value} %", font=_font("bold", 38), fill=WHITE, anchor="rm")


def render_board(entries: list[Entry], page: int, pages: int, players: int, footer: str) -> bytes:
    podium = [entry for entry in entries if entry.rank <= 3] if page == 1 else []
    rows = [entry for entry in entries if entry not in podium]
    body_top = 270
    height = body_top + (PODIUM_HEIGHT if podium else 0) + len(rows) * (ROW_HEIGHT + ROW_GAP) + 90
    image = _background(height)
    _header(image, players, page, pages)
    if podium:
        _podium(image, podium, body_top)
    _rows(image, rows, body_top + (PODIUM_HEIGHT if podium else 0))
    ImageDraw.Draw(image).text((WIDTH / 2, height - 45), footer, font=_font("regular", 22), fill=MUTED, anchor="mm")

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
