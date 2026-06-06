import logging
import random
import time
from pathlib import Path

import httpx

from bot import user
from bot.config import config
from bot.features import get_state, set_trap_assets_version, set_trap_photo
from bot.vk_photo import prepare_trap_panel
from bot.vk_rate import throttle

logger = logging.getLogger(__name__)

TRAP_TOP_PATH = Path(__file__).parent / "assets" / "trap" / "top.png"
TRAP_BOTTOM_PATH = Path(__file__).parent / "assets" / "trap" / "bottom.png"

TRAP_BAIT = "знаешь что топ?"
TRAP_CLOSER = "думаю ты понял"
TRAP_TIMEOUT_SEC = 300
TRAP_GRACE_SEC = 3
TRAP_ASSETS_VERSION = 2

_armed_traps: dict[int, float] = {}


def arm_trap(peer_id: int) -> None:
    _armed_traps[peer_id] = time.monotonic()
    logger.info("Trap armed for peer=%s", peer_id)


def get_trap_armed_at(peer_id: int | None) -> float | None:
    if not peer_id:
        return None
    return _armed_traps.get(peer_id)


def is_trap_armed(peer_id: int | None) -> bool:
    if not peer_id:
        return False
    armed_at = _armed_traps.get(peer_id)
    if armed_at is None:
        return False
    if time.monotonic() - armed_at > TRAP_TIMEOUT_SEC:
        _armed_traps.pop(peer_id, None)
        return False
    return True


def is_trap_grace_period(peer_id: int | None) -> bool:
    armed_at = get_trap_armed_at(peer_id)
    if armed_at is None:
        return False
    return time.monotonic() - armed_at < TRAP_GRACE_SEC


def should_catch_trap_message(
    *,
    peer_id: int | None,
    from_id: int | None,
    self_id: int,
    text: str | None,
    out: int,
) -> bool:
    if not is_trap_armed(peer_id):
        return False
    if match_prefixed_command(text or "", "ловушка"):
        return False
    if (text or "").strip().lower() == TRAP_BAIT.lower():
        return False

    if from_id == self_id:
        if is_trap_grace_period(peer_id):
            return False
        return True

    return out == 0


def disarm_trap(peer_id: int | None) -> None:
    if peer_id:
        _armed_traps.pop(peer_id, None)


def match_prefixed_command(text: str, command: str) -> bool:
    state = get_state()
    prefix = state.command_prefix.strip().lower()
    if not prefix:
        return False
    normalized = (text or "").strip().lower()
    return normalized in {f"{prefix} {command}", f"{prefix}{command}"}


async def _upload_message_photo(peer_id: int, image_bytes: bytes, filename: str) -> str:
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


async def get_trap_photo(peer_id: int, which: str) -> str:
    state = get_state()
    cached = getattr(state, f"trap_photo_{which}", "")
    if cached and state.trap_assets_version == TRAP_ASSETS_VERSION:
        return cached

    path = TRAP_TOP_PATH if which == "top" else TRAP_BOTTOM_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Trap image missing: {path}")

    image_bytes = prepare_trap_panel(path, panel=which)
    attachment = await _upload_message_photo(
        peer_id,
        image_bytes,
        filename=f"trap_{which}.jpg",
    )
    set_trap_photo(which, attachment)
    state = get_state()
    if state.trap_photo_top and state.trap_photo_bottom:
        set_trap_assets_version(TRAP_ASSETS_VERSION)
    logger.info("Uploaded trap %s photo (%d bytes): %s", which, len(image_bytes), attachment)
    return attachment


async def _send(peer_id: int, *, message: str = "", attachment: str | None = None) -> None:
    await throttle()
    await user.api.messages.send(
        peer_id=peer_id,
        message=message,
        attachment=attachment,
        random_id=random.randint(1, 2_000_000_000),
    )


async def start_trap(peer_id: int) -> None:
    top_photo = await get_trap_photo(peer_id, "top")
    await get_trap_photo(peer_id, "bottom")

    await _send(peer_id, message=TRAP_BAIT)
    await _send(peer_id, attachment=top_photo)
    arm_trap(peer_id)


async def finish_trap(peer_id: int) -> None:
    disarm_trap(peer_id)
    bottom_photo = await get_trap_photo(peer_id, "bottom")
    await _send(peer_id, attachment=bottom_photo)
    await _send(peer_id, message=TRAP_CLOSER)
