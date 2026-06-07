import io
import logging
from pathlib import Path

import httpx
from PIL import Image

from bot import user
from bot.config import config
from bot.vk_rate import throttle

logger = logging.getLogger(__name__)

# VK в ленте сообщений показывает фото с шириной до 960px — оба кадра ловушки
# должны быть одинакового размера, иначе полоски не сойдутся («960 crop»).
VK_MESSAGE_WIDTH = 960
VK_TRAP_PANEL_HEIGHT = 480


def prepare_trap_panel(source: Path, *, panel: str) -> bytes:
    """Готовит JPEG 960×480 для загрузки в messages (без crop-параметров API)."""
    if panel not in {"top", "bottom"}:
        raise ValueError(f"unknown trap panel: {panel}")

    with Image.open(source) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size

        scale = VK_MESSAGE_WIDTH / width
        scaled_h = max(1, round(height * scale))
        resized = rgb.resize((VK_MESSAGE_WIDTH, scaled_h), Image.Resampling.LANCZOS)

        if scaled_h < VK_TRAP_PANEL_HEIGHT:
            canvas = Image.new("RGB", (VK_MESSAGE_WIDTH, VK_TRAP_PANEL_HEIGHT), (0, 0, 0))
            if panel == "top":
                canvas.paste(resized, (0, 0))
            else:
                canvas.paste(resized, (0, VK_TRAP_PANEL_HEIGHT - scaled_h))
            result = canvas
        elif scaled_h > VK_TRAP_PANEL_HEIGHT:
            if panel == "top":
                top = scaled_h - VK_TRAP_PANEL_HEIGHT
            else:
                top = 0
            result = resized.crop((0, top, VK_MESSAGE_WIDTH, top + VK_TRAP_PANEL_HEIGHT))
        else:
            result = resized

    buffer = io.BytesIO()
    result.save(buffer, format="JPEG", quality=92, optimize=True)
    data = buffer.getvalue()
    logger.debug(
        "Prepared trap %s panel: %s -> %dx%d (%d bytes)",
        panel,
        source.name,
        VK_MESSAGE_WIDTH,
        VK_TRAP_PANEL_HEIGHT,
        len(data),
    )
    return data


async def upload_message_photo(
    peer_id: int, image_bytes: bytes, filename: str = "image.jpg"
) -> str:
    await throttle()
    upload_server = await user.api.photos.get_messages_upload_server(peer_id=peer_id)

    async with httpx.AsyncClient(verify=config.ssl_verify, timeout=60.0) as client:
        response = await client.post(
            upload_server.upload_url,
            files={"photo": (filename, image_bytes, "image/jpeg")},
        )
        response.raise_for_status()
        data = response.json()

    if not data.get("photo") or not data.get("server") or not data.get("hash"):
        raise RuntimeError(f"VK photo upload failed: {data}")

    await throttle()
    saved = await user.api.photos.save_messages_photo(
        photo=data["photo"],
        server=data["server"],
        hash=data["hash"],
    )
    photo = saved[0]
    attachment = f"photo{photo.owner_id}_{photo.id}"
    if photo.access_key:
        attachment += f"_{photo.access_key}"
    return attachment
