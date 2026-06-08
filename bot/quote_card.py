"""Генерация карточки-цитаты из сообщения ВК."""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw, ImageFont
from vkbottle_types.objects import UsersFields

from bot import get_api
from bot.config import config
from bot.media import VK_CDN_HEADERS

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
WIDTH = 1280
HEIGHT = 720

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
TEMPLATE_BG = ASSETS_DIR / "quote_reference.png"

FONT_QUOTE_CYR = FONTS_DIR / "nunito-regular.ttf"
FONT_QUOTE_LAT = FONTS_DIR / "nunito-latin.ttf"
FONT_NAME_CYR = FONTS_DIR / "nunito-semibold.ttf"
FONT_NAME_LAT = FONTS_DIR / "nunito-latin-600.ttf"
FONT_MARK = FONTS_DIR / "bebas-neue.ttf"

AVATAR_SIZE = 290
AVATAR_X = 230
AVATAR_Y = 318
NAME_Y = 518
DATE_Y = 558
FOOTER_AVATAR_SIZE = 34

MONTHS_EN = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

BLACK = (0, 0, 0)
TEXT = (255, 255, 255)


def message_date_to_timestamp(value: object) -> int:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return int(value.replace(tzinfo=MSK).timestamp())
        return int(value.timestamp())
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def format_message_date(timestamp: int) -> str:
    dt = datetime.fromtimestamp(timestamp, MSK)
    month = MONTHS_EN[dt.month]
    return f"{dt.day:02d} {month} {dt.year}, {dt.strftime('%H:%M')}"


def _upgrade_photo_url(url: str) -> str:
    if "cs=" in url:
        return re.sub(r"cs=\d+x\d+", "cs=540x540", url)
    return url


def _extract_photo_url(photo: object) -> str | None:
    if photo is None:
        return None
    if isinstance(photo, str):
        value = photo.strip()
        return _upgrade_photo_url(value) if value else None

    sizes = getattr(photo, "sizes", None)
    if sizes:
        best = max(sizes, key=lambda item: getattr(item, "width", 0) or 0)
        url = getattr(best, "url", None)
        if url:
            return _upgrade_photo_url(url)

    for attr in ("url", "src", "photo_604", "photo_200"):
        url = getattr(photo, attr, None)
        if isinstance(url, str) and url.strip():
            return _upgrade_photo_url(url.strip())
    return None


async def _download_image(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(verify=config.ssl_verify, timeout=30.0) as client:
            response = await client.get(url, headers=VK_CDN_HEADERS, follow_redirects=True)
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        logger.warning("Avatar download failed for %s: %s", url[:80], exc)
        return None


async def fetch_author_avatar(user_id: int) -> bytes | None:
    if user_id < 0:
        return await _fetch_group_avatar(-user_id)

    try:
        profiles = await get_api().users.get(
            user_ids=[user_id],
            fields=[
                UsersFields.PHOTO_MAX_ORIG,
                UsersFields.PHOTO_MAX,
                UsersFields.PHOTO_200,
            ],
        )
    except Exception as exc:
        logger.warning("users.get for quote avatar failed: %s", exc)
        return None

    if not profiles:
        return None

    profile = profiles[0]
    url = (
        _extract_photo_url(getattr(profile, "photo_max_orig", None))
        or _extract_photo_url(profile.photo_max)
        or _extract_photo_url(profile.photo_200)
    )
    if not url:
        logger.warning("No avatar URL for user_id=%s", user_id)
        return None

    data = await _download_image(url)
    if data:
        logger.info("Avatar loaded for user_id=%s (%s bytes)", user_id, len(data))
    return data


async def _fetch_group_avatar(group_id: int) -> bytes | None:
    try:
        groups = await get_api().groups.get_by_id(group_id=group_id, fields=["photo_max", "photo_200"])
    except Exception as exc:
        logger.warning("groups.getById for quote avatar failed: %s", exc)
        return None

    if not groups:
        return None

    group = groups[0] if isinstance(groups, list) else groups
    url = _extract_photo_url(getattr(group, "photo_max", None)) or _extract_photo_url(
        getattr(group, "photo_200", None)
    )
    if not url:
        return None
    return await _download_image(url)


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        logger.warning("Font missing: %s", path)
        return ImageFont.load_default()


def _is_cyrillic(char: str) -> bool:
    code = ord(char)
    return 0x0400 <= code <= 0x052F


def _glyph_font(char: str, size: int, *, strong: bool = False) -> ImageFont.ImageFont:
    if _is_cyrillic(char):
        return _load_font(FONT_NAME_CYR if strong else FONT_QUOTE_CYR, size)
    return _load_font(FONT_NAME_LAT if strong else FONT_QUOTE_LAT, size)


def _text_width(text: str, size: int, draw: ImageDraw.ImageDraw, *, strong: bool = False) -> float:
    return sum(draw.textlength(char, font=_glyph_font(char, size, strong=strong)) for char in text)


def _draw_text_line(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    size: int,
    fill: tuple[int, int, int],
    *,
    strong: bool = False,
    centered: bool = False,
) -> None:
    x, y = xy
    if centered:
        x -= int(_text_width(text, size, draw, strong=strong) // 2)

    for char in text:
        font = _glyph_font(char, size, strong=strong)
        draw.text((x, y), char, fill=fill, font=font)
        x += int(draw.textlength(char, font=font))


def _circle_avatar(image: Image.Image, size: int) -> Image.Image:
    fitted = image.convert("RGBA")
    fitted = fitted.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(fitted, (0, 0), mask)
    return output


def _placeholder_avatar(size: int, label: str) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(38, 50, 66, 255))
    letter = (label or "?")[:1].upper()
    font = _glyph_font(letter, max(28, size // 3), strong=True)
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, (size - th) // 2 - 2), letter, fill=TEXT, font=font)
    return image


def _wrap_text(
    text: str,
    size: int,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_width(candidate, size, draw) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


@lru_cache(maxsize=1)
def _background_image() -> Image.Image:
    if not TEMPLATE_BG.exists():
        return Image.new("RGB", (WIDTH, HEIGHT), BLACK)

    ref = Image.open(TEMPLATE_BG).convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    image = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    edge = 96
    image.paste(ref.crop((0, 0, edge, HEIGHT)), (0, 0))
    image.paste(ref.crop((WIDTH - edge, 0, WIDTH, HEIGHT)), (WIDTH - edge, 0))
    image.paste(ref.crop((0, 0, WIDTH, 54)), (0, 0))
    image.paste(ref.crop((0, HEIGHT - 54, WIDTH, HEIGHT)), (0, HEIGHT - 54))
    return image


def _draw_footer(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    footer_avatar_bytes: bytes | None,
) -> None:
    label = ">%+ default xP_"
    label_width = int(_text_width(label, 22, draw, strong=True))
    footer_x = WIDTH - label_width - 72
    footer_y = HEIGHT - 54

    _draw_text_line(draw, (footer_x, footer_y), label, 22, TEXT, strong=True)

    if footer_avatar_bytes:
        with Image.open(io.BytesIO(footer_avatar_bytes)) as source:
            mini = _circle_avatar(source, FOOTER_AVATAR_SIZE)
        image.paste(mini, (footer_x + label_width + 10, footer_y - 6), mini)


def generate_quote_card(
    *,
    author_name: str,
    quote_text: str,
    message_date: int,
    avatar_bytes: bytes | None,
    footer_avatar_bytes: bytes | None = None,
) -> bytes:
    image = _background_image().copy()
    draw = ImageDraw.Draw(image)

    if avatar_bytes:
        with Image.open(io.BytesIO(avatar_bytes)) as source:
            avatar = _circle_avatar(source, AVATAR_SIZE)
    else:
        avatar = _placeholder_avatar(AVATAR_SIZE, author_name)

    image.paste(
        avatar,
        (AVATAR_X - AVATAR_SIZE // 2, AVATAR_Y - AVATAR_SIZE // 2),
        avatar,
    )

    name = author_name.strip() or "Пользователь"
    _draw_text_line(draw, (AVATAR_X, NAME_Y), name, 34, TEXT, strong=True, centered=True)
    _draw_text_line(
        draw,
        (AVATAR_X, DATE_Y),
        format_message_date(message_date),
        24,
        TEXT,
        strong=True,
        centered=True,
    )

    quote_left = 360
    quote_right = WIDTH - 360
    max_width = quote_right - quote_left - 60

    font_size = 54
    line_height = 66
    while True:
        lines = _wrap_text(quote_text.strip() or "…", font_size, max_width, draw)
        block_height = len(lines) * line_height
        if block_height <= 300 or font_size <= 30:
            break
        font_size -= 2

    block_top = (HEIGHT - block_height) // 2
    mark_font = _load_font(FONT_MARK, 160)
    open_x = quote_left + 4
    open_y = block_top - 64
    draw.text((open_x, open_y), "\u201c", fill=TEXT, font=mark_font)

    for index, line in enumerate(lines):
        line_width = int(_text_width(line, font_size, draw))
        line_x = (WIDTH - line_width) // 2
        _draw_text_line(draw, (line_x, block_top + index * line_height), line, font_size, TEXT)

    last_line = lines[-1]
    close_x = (WIDTH + int(_text_width(last_line, font_size, draw))) // 2 + 24
    close_y = block_top + block_height - 6
    draw.text((close_x, close_y), "\u201d", fill=TEXT, font=mark_font)

    _draw_footer(image, draw, footer_avatar_bytes=footer_avatar_bytes)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=94, optimize=True)
    return buffer.getvalue()
