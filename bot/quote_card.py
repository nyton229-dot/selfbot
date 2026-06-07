"""Генерация карточки-цитаты из сообщения ВК."""

from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw, ImageFont
from vkbottle_types.objects import UsersFields

from bot import user
from bot.config import config

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
WIDTH = 1100
HEIGHT = 620
FONT_PATH = Path(__file__).resolve().parent / "assets" / "fonts" / "bebas-neue.ttf"

MONTHS_RU = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

BG = (8, 12, 18)
PANEL = (10, 42, 58)
ACCENT = (34, 211, 238)
TEXT = (245, 248, 255)
MUTED = (148, 163, 184)


def format_message_date(timestamp: int) -> str:
    dt = datetime.fromtimestamp(timestamp, MSK)
    month = MONTHS_RU[dt.month]
    return f"{dt.day:02d} {month} {dt.year}, {dt.strftime('%H:%M')}"


async def fetch_author_avatar(user_id: int) -> bytes | None:
    try:
        profiles = await user.api.users.get(
            user_ids=[user_id],
            fields=[UsersFields.PHOTO_200, UsersFields.PHOTO_MAX],
        )
    except Exception as exc:
        logger.warning("users.get for quote avatar failed: %s", exc)
        return None

    if not profiles:
        return None

    profile = profiles[0]
    photo = profile.photo_max or profile.photo_200
    if not photo:
        return None

    url = None
    if photo.sizes:
        url = max(photo.sizes, key=lambda item: item.width or 0).url
    if not url:
        return None

    try:
        async with httpx.AsyncClient(verify=config.ssl_verify, timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        logger.warning("Avatar download failed: %s", exc)
        return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        return ImageFont.load_default()


def _circle_avatar(image: Image.Image, size: int) -> Image.Image:
    fitted = image.convert("RGBA")
    fitted = fitted.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(fitted, (0, 0), mask)
    return output


def _placeholder_avatar(size: int, label: str) -> Image.Image:
    image = Image.new("RGBA", (size, size), (30, 41, 59, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(51, 65, 85, 255))
    font = _load_font(max(28, size // 3))
    letter = (label or "?")[:1].upper()
    bbox = draw.textbbox((0, 0), letter, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((size - tw) // 2, (size - th) // 2 - 4),
        letter,
        fill=TEXT,
        font=font,
    )
    return image


def _draw_circuit_panel(draw: ImageDraw.ImageDraw, x0: int, x1: int) -> None:
    for y in range(20, HEIGHT - 20, 34):
        draw.line((x0, y, x1, y), fill=(18, 78, 96), width=1)
    for x in range(x0 + 8, x1, 28):
        for y in range(30, HEIGHT - 30, 52):
            draw.ellipse((x, y, x + 4, y + 4), fill=ACCENT)
            if x + 14 < x1:
                draw.line((x + 4, y + 2, x + 18, y + 2), fill=(24, 120, 140), width=1)


def _draw_border(draw: ImageDraw.ImageDraw, y: int) -> None:
    draw.line((70, y, WIDTH - 70, y), fill=(226, 232, 240), width=2)
    cx = WIDTH // 2
    draw.polygon(
        [(cx, y - 8), (cx + 10, y), (cx, y + 8), (cx - 10, y)],
        fill=TEXT,
    )


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_footer(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    footer_text: str,
    footer_avatar_bytes: bytes | None,
) -> None:
    footer_font = _load_font(20)
    label = f">%+ {footer_text} xP_"
    label_width = int(draw.textlength(label, font=footer_font))
    footer_x = WIDTH - label_width - 58
    footer_y = HEIGHT - 52

    if footer_avatar_bytes:
        with Image.open(io.BytesIO(footer_avatar_bytes)) as source:
            mini = _circle_avatar(source, 34)
        image.paste(mini, (footer_x - 42, footer_y - 4), mini)

    draw.text((footer_x, footer_y), label, fill=MUTED, font=footer_font)


def generate_quote_card(
    *,
    author_name: str,
    quote_text: str,
    message_date: int,
    avatar_bytes: bytes | None,
    footer_text: str = "quote",
    footer_avatar_bytes: bytes | None = None,
) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, 130, HEIGHT), fill=PANEL)
    draw.rectangle((WIDTH - 130, 0, WIDTH, HEIGHT), fill=PANEL)
    _draw_circuit_panel(draw, 8, 122)
    _draw_circuit_panel(draw, WIDTH - 122, WIDTH - 8)
    _draw_border(draw, 36)
    _draw_border(draw, HEIGHT - 36)

    avatar_size = 170
    avatar_x = 78
    avatar_y = 118
    if avatar_bytes:
        with Image.open(io.BytesIO(avatar_bytes)) as source:
            avatar = _circle_avatar(source, avatar_size)
    else:
        avatar = _placeholder_avatar(avatar_size, author_name)

    image.paste(avatar, (avatar_x, avatar_y), avatar)

    name_font = _load_font(34)
    date_font = _load_font(22)
    name = author_name.strip() or "Пользователь"
    draw.text((avatar_x, avatar_y + avatar_size + 18), name, fill=TEXT, font=name_font)
    draw.text(
        (avatar_x, avatar_y + avatar_size + 58),
        format_message_date(message_date),
        fill=MUTED,
        font=date_font,
    )

    mark_font = _load_font(120)
    text_left = 300
    text_right = WIDTH - 90
    max_width = text_right - text_left

    font_size = 54
    line_height = 62
    while True:
        quote_font = _load_font(font_size)
        lines = _wrap_text(quote_text.strip() or "…", quote_font, max_width, draw)
        block_height = len(lines) * line_height
        if block_height <= 280 or font_size <= 30:
            break
        font_size -= 4

    text_top = (HEIGHT - block_height) // 2 + 10
    draw.text((text_left - 8, text_top - 70), "“", fill=TEXT, font=mark_font)
    for index, line in enumerate(lines):
        draw.text(
            (text_left, text_top + index * line_height),
            line,
            fill=TEXT,
            font=quote_font,
        )
    closing_y = text_top + block_height - 10
    closing_x = min(text_right - 20, text_left + int(draw.textlength(lines[-1], font=quote_font)) + 30)
    draw.text((closing_x, closing_y), "”", fill=TEXT, font=mark_font)
    _draw_footer(
        image,
        draw,
        footer_text=footer_text,
        footer_avatar_bytes=footer_avatar_bytes,
    )

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    return buffer.getvalue()
