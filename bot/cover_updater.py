"""Динамическая обложка личной страницы ВК (user token + user_id)."""

from __future__ import annotations

import io
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw, ImageFont

from bot import get_self_id, user
from bot.config import config
from bot.vk_rate import throttle

logger = logging.getLogger(__name__)

# Стандартный размер обложки профиля ВК
WIDTH = 1920
HEIGHT = 768

FONT_PATH = Path(__file__).resolve().parent / "assets" / "fonts" / "bebas-neue.ttf"
BACKGROUND_PATH = Path(__file__).resolve().parent / "assets" / "cover" / "background.png"
MSK = ZoneInfo("Europe/Moscow")


def msk_now() -> datetime:
    """Текущее время по Москве (независимо от часового пояса сервера)."""
    return datetime.now(MSK)


async def sleep_until_next_msk_minute() -> None:
    """Ждёт до начала следующей минуты по МСК."""
    now = msk_now()
    wait = 60 - now.second - now.microsecond / 1_000_000
    if wait <= 0.05:
        wait = 60
    await asyncio.sleep(wait)


def _fit_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    """Масштабирует и обрезает фото под 1920×768 без искажений."""
    src_w, src_h = image.size
    scale = max(width / src_w, height / src_h)
    new_w = round(src_w * scale)
    new_h = round(src_h * scale)
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _load_background() -> Image.Image:
    if not BACKGROUND_PATH.is_file():
        raise FileNotFoundError(f"Cover background missing: {BACKGROUND_PATH}")
    with Image.open(BACKGROUND_PATH) as source:
        return _fit_cover(source.convert("RGB"), WIDTH, HEIGHT)


def generate_cover_image() -> bytes:
    """Генерирует JPEG 1920×768: фон + время и дата."""
    image = _load_background()
    draw = ImageDraw.Draw(image)

    now = msk_now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%d.%m.%Y")

    try:
        font_time = ImageFont.truetype(str(FONT_PATH), 230)
        font_sub = ImageFont.truetype(str(FONT_PATH), 88)
    except OSError:
        logger.warning("Bebas Neue not found at %s, using default font", FONT_PATH)
        font_time = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    text_kw = {"stroke_width": 4, "stroke_fill": "#0f172a"}
    draw.text(
        (WIDTH // 2, 320),
        time_str,
        fill="#ffffff",
        font=font_time,
        anchor="mm",
        **text_kw,
    )
    draw.text(
        (WIDTH // 2, 472),
        date_str,
        fill="#f1f5f9",
        font=font_sub,
        anchor="mm",
        stroke_width=3,
        stroke_fill="#0f172a",
    )

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    return buffer.getvalue()


def _extract_upload_url(payload: Any) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        if "upload_url" in payload:
            return payload["upload_url"]
        if "response" in payload:
            return _extract_upload_url(payload["response"])
        return None
    return getattr(payload, "upload_url", None)


async def upload_profile_cover(image_bytes: bytes) -> None:
    """
    Загружает обложку на личную страницу владельца токена.

    Для профиля пользователя VK принимает user_id + crop_width/crop_height.
    crop_x2/crop_y2 — только для обложек сообществ (group_id).
    """
    user_id = await get_self_id()

    await throttle()
    server_payload = await user.api.request(
        "photos.getOwnerCoverPhotoUploadServer",
        {
            "user_id": user_id,
            "crop_width": WIDTH,
            "crop_height": HEIGHT,
        },
    )
    upload_url = _extract_upload_url(server_payload)
    if not upload_url:
        raise RuntimeError(f"VK не вернул upload_url: {server_payload}")

    async with httpx.AsyncClient(verify=config.ssl_verify, timeout=60.0) as client:
        response = await client.post(
            upload_url,
            files={"photo": ("cover.jpg", image_bytes, "image/jpeg")},
        )
        response.raise_for_status()
        data = response.json()

    if not data.get("photo") or not data.get("hash"):
        raise RuntimeError(f"Ошибка загрузки на сервер VK: {data}")

    await throttle()
    await user.api.photos.save_owner_cover_photo(
        hash=data["hash"],
        photo=data["photo"],
    )


async def update_profile_cover() -> None:
    """Сгенерировать и установить обложку на свою страницу."""
    user_id = await get_self_id()
    image_bytes = generate_cover_image()
    await upload_profile_cover(image_bytes)
    logger.info(
        "Profile cover updated for user_id=%s at %s MSK (%d bytes)",
        user_id,
        msk_now().strftime("%H:%M"),
        len(image_bytes),
    )
