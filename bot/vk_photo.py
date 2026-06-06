import io
import logging
from pathlib import Path

from PIL import Image

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
