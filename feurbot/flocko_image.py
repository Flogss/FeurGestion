"""Image du /topflocko, style mème / BD : fond jaune à trames, bulles « quoi ? » / « feur. », cases à bord noir.

Pas de flou ni de dégradé coûteux : le fond est calculé une fois puis réutilisé, et l'image part en JPEG.
"""

import io
import os
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

WIDTH = 900
PAD = 40
ROW_HEIGHT = 84
ROW_GAP = 18
HEADER_HEIGHT = 250
PODIUM_HEIGHT = 420
BOTTOM = 34

INK = (27, 27, 27)
YELLOW = (255, 210, 63)
DOTS = (247, 197, 45)
WHITE = (255, 255, 255)
GREY = (110, 110, 110)
GOLD = (255, 195, 0)
SILVER = (192, 199, 209)
BRONZE = (224, 142, 69)
MEDALS = {1: GOLD, 2: SILVER, 3: BRONZE}
AVATAR_COLORS = [(255, 79, 121), (58, 134, 255), (46, 196, 182), (255, 159, 28), (155, 93, 229), (241, 91, 181)]

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
        if char not in "‍️" and unicodedata.category(char) not in ("So", "Sk", "Cs", "Co", "Cn", "Cf")
    ]
    return " ".join("".join(kept).split()) or "Anonyme"


def _fit(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: float) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _bar_color(value: int) -> tuple[int, int, int]:
    if value >= 100:
        return GOLD
    if value >= 67:
        return (46, 196, 182)
    if value >= 34:
        return (255, 159, 28)
    return (255, 79, 121)


@lru_cache(maxsize=8)
def _background(height: int) -> Image.Image:
    """Fond jaune avec une trame de points façon BD (calculé une fois par hauteur)."""
    image = Image.new("RGB", (WIDTH, height), YELLOW)
    draw = ImageDraw.Draw(image)
    step = 22
    for row, y in enumerate(range(0, height + step, step)):
        offset = step // 2 if row % 2 else 0
        for x in range(-step + offset, WIDTH + step, step):
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=DOTS)
    return image


def _panel(draw: ImageDraw.ImageDraw, box, fill=WHITE, radius=18, border=4, shadow=7) -> None:
    """Case de BD : ombre noire décalée, fond, contour épais."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 + shadow, y0 + shadow, x1 + shadow, y1 + shadow), radius=radius, fill=INK)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=INK, width=border)


def _bubble(draw: ImageDraw.ImageDraw, center, text: str, size: int, tail: str) -> None:
    """Bulle de dialogue blanche avec sa petite queue."""
    font = _font("bold", size)
    width = draw.textlength(text, font=font) + size * 1.4
    height = size * 1.9
    x, y = center
    box = (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
    tip_x = box[0] + width * 0.3 if tail == "left" else box[2] - width * 0.3
    direction = -1 if tail == "left" else 1
    tail_points = [(tip_x - 12, box[3] - 6), (tip_x + 12, box[3] - 6), (tip_x + direction * 24, box[3] + 24)]
    draw.polygon(tail_points, fill=WHITE)
    draw.line([tail_points[0], tail_points[2], tail_points[1]], fill=INK, width=4, joint="curve")
    draw.rounded_rectangle(box, radius=height / 2, fill=WHITE, outline=INK, width=4)
    # On efface le contour de la bulle à la jonction avec la queue
    draw.line([(tail_points[0][0] + 3, box[3] - 2), (tail_points[1][0] - 3, box[3] - 2)], fill=WHITE, width=5)
    draw.text((x, y), text, font=font, fill=INK, anchor="mm")


def _avatar(entry: Entry, size: int) -> Image.Image:
    picture = None
    if entry.avatar:
        try:
            picture = Image.open(io.BytesIO(entry.avatar)).convert("RGB").resize((size, size), Image.BILINEAR)
        except OSError:
            picture = None
    if picture is None:
        picture = Image.new("RGB", (size, size), AVATAR_COLORS[entry.user_id % len(AVATAR_COLORS)])
        ImageDraw.Draw(picture).text(
            (size / 2, size / 2), clean_name(entry.name)[0].upper(), font=_font("bold", int(size * 0.46)),
            fill=WHITE, anchor="mm", stroke_width=max(2, size // 30), stroke_fill=INK,
        )
    mask = Image.new("L", (size * 3, size * 3), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 3, size * 3), fill=255)
    rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded.paste(picture, (0, 0), mask.resize((size, size), Image.BILINEAR))
    return rounded


def _paste_avatar(image: Image.Image, entry: Entry, center, size: int, ring) -> None:
    x, y = center
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - size / 2 - 7, y - size / 2 - 7, x + size / 2 + 7, y + size / 2 + 7), fill=INK)
    draw.ellipse((x - size / 2 - 4, y - size / 2 - 4, x + size / 2 + 4, y + size / 2 + 4), fill=ring)
    avatar = _avatar(entry, size)
    image.paste(avatar, (round(x - size / 2), round(y - size / 2)), avatar)


def _badge(draw: ImageDraw.ImageDraw, center, radius: int, rank: int) -> None:
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=MEDALS.get(rank, INK), outline=INK, width=4)
    size = int(radius * (1.0 if rank < 100 else 0.75))
    color = INK if rank in MEDALS else YELLOW
    draw.text((x, y + 1), str(rank), font=_font("bold", size), fill=color, anchor="mm")


def _header(image: Image.Image, players: int, page: int, pages: int) -> None:
    # Titre façon mème (blanc cerné de noir), légèrement penché
    layer = Image.new("RGBA", (WIDTH, 150), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(
        (WIDTH / 2, 75), "TOP FLOCKO", font=_font("bold", 92), fill=WHITE, anchor="mm", stroke_width=8, stroke_fill=INK
    )
    layer = layer.rotate(3, resample=Image.BICUBIC)
    image.paste(layer, (0, 64), layer)

    draw = ImageDraw.Draw(image)
    _bubble(draw, (150, 46), "quoi ?", 30, "left")
    _bubble(draw, (WIDTH - 150, 52), "feur.", 30, "right")

    subtitle = f"feurchat · {players} joueur{'s' if players > 1 else ''} · page {page}/{pages}"
    font = _font("bold", 24)
    width = draw.textlength(subtitle, font=font) + 44
    draw.rounded_rectangle(((WIDTH - width) / 2, 204, (WIDTH + width) / 2, 242), radius=19, fill=INK)
    draw.text((WIDTH / 2, 223), subtitle, font=font, fill=YELLOW, anchor="mm")


def _crown(draw: ImageDraw.ImageDraw, center) -> None:
    x, y = center
    points = [(x - 30, y + 16), (x - 30, y - 8), (x - 15, y + 4), (x, y - 18), (x + 15, y + 4), (x + 30, y - 8), (x + 30, y + 16)]
    draw.polygon(points, fill=GOLD)
    draw.line(points + [points[0]], fill=INK, width=4, joint="curve")


def _podium(image: Image.Image, entries: list[Entry], top: int) -> None:
    """Trois cases posées sur des marches : la plus haute pour le 1er."""
    draw = ImageDraw.Draw(image)
    by_rank = {entry.rank: entry for entry in entries}
    base = top + PODIUM_HEIGHT - 26
    # (rang, centre x, largeur, taille de l'avatar, hauteur de la marche)
    spots = [(2, WIDTH / 2 - 285, 250, 104, 76), (1, WIDTH / 2, 270, 124, 110), (3, WIDTH / 2 + 285, 250, 104, 54)]
    for rank, x, width, size, step in spots:
        entry = by_rank.get(rank)
        if entry is None:
            continue
        content = 20 + size + 14 + 40 + 56
        box = (x - width / 2, base - step - content, x + width / 2, base)
        _panel(draw, box)
        color = MEDALS[rank]
        draw.rounded_rectangle((box[0], base - step, box[2], base), radius=18, fill=color, outline=INK, width=4)
        draw.text((x, base - step / 2), f"#{rank}", font=_font("bold", 38 if rank == 1 else 32), fill=INK, anchor="mm")

        center_y = box[1] + 20 + 7 + size / 2
        _paste_avatar(image, entry, (x, center_y), size, color)
        if rank == 1:
            _crown(draw, (x, box[1] - 2))
        name_y = center_y + size / 2 + 7 + 22
        name_font = _font("bold", 26)
        draw.text((x, name_y), _fit(draw, clean_name(entry.name), name_font, width - 30), font=name_font, fill=INK, anchor="mm")
        draw.text(
            (x, name_y + 44), f"{entry.value} %", font=_font("bold", 48 if rank == 1 else 42),
            fill=_bar_color(entry.value), anchor="mm", stroke_width=3, stroke_fill=INK,
        )


def _rows(image: Image.Image, entries: list[Entry], top: int) -> None:
    draw = ImageDraw.Draw(image)
    bar_left, bar_right = 520, WIDTH - PAD - 124
    for index, entry in enumerate(entries):
        y = top + index * (ROW_HEIGHT + ROW_GAP)
        middle = y + ROW_HEIGHT / 2
        _panel(draw, (PAD, y, WIDTH - PAD - 8, y + ROW_HEIGHT), radius=16, border=4, shadow=6)
        _badge(draw, (PAD + 42, middle), 25, entry.rank)
        _paste_avatar(image, entry, (PAD + 116, middle), 54, MEDALS.get(entry.rank, YELLOW))
        name_font = _font("bold", 28)
        name = _fit(draw, clean_name(entry.name), name_font, bar_left - PAD - 180)
        draw.text((PAD + 160, middle - 13), name, font=name_font, fill=INK, anchor="lm")
        draw.text((PAD + 160, middle + 19), entry.date, font=_font("regular", 19), fill=GREY, anchor="lm")
        draw.rounded_rectangle((bar_left, middle - 11, bar_right, middle + 11), radius=11, fill=(238, 238, 238), outline=INK, width=3)
        if entry.value:
            fill_right = max(bar_left + (bar_right - bar_left) * entry.value / 100, bar_left + 22)
            draw.rounded_rectangle((bar_left, middle - 11, fill_right, middle + 11), radius=11,
                                   fill=_bar_color(entry.value), outline=INK, width=3)
        draw.text((WIDTH - PAD - 26, middle), f"{entry.value} %", font=_font("bold", 32), fill=INK, anchor="rm")


def render_board(entries: list[Entry], page: int, pages: int, players: int) -> bytes:
    podium = [entry for entry in entries if entry.rank <= 3] if page == 1 else []
    rows = [entry for entry in entries if entry not in podium]
    height = HEADER_HEIGHT + (PODIUM_HEIGHT if podium else 10) + len(rows) * (ROW_HEIGHT + ROW_GAP) + BOTTOM
    image = _background(height).copy()
    _header(image, players, page, pages)
    if podium:
        _podium(image, podium, HEADER_HEIGHT)
    _rows(image, rows, HEADER_HEIGHT + (PODIUM_HEIGHT if podium else 10))

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85)
    return output.getvalue()
