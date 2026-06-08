import logging
import re

from vkbottle.user import Message

from bot import get_api
from bot.replies import resolve_reply_from_id

logger = logging.getLogger(__name__)

ID_MENTION_RE = re.compile(r"\[id(-?\d+)\|", re.IGNORECASE)
URL_ID_RE = re.compile(r"(?:https?://)?(?:m\.)?(?:vk\.com|vk\.ru)/id(\d+)", re.IGNORECASE)
URL_DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:m\.)?(?:vk\.com|vk\.ru)/([a-zA-Z0-9_.]+)",
    re.IGNORECASE,
)


async def resolve_user_id(message: Message, arg: str | None) -> int | None:
    if arg:
        user_id = await _resolve_from_text(arg)
        if user_id:
            return user_id

    return await resolve_reply_from_id(message)


async def _resolve_from_text(text: str) -> int | None:
    raw = (text or "").strip()
    if not raw:
        return None

    match = ID_MENTION_RE.search(raw)
    if match:
        return int(match.group(1))

    if raw.lstrip("-").isdigit():
        return int(raw)

    match = URL_ID_RE.search(raw)
    if match:
        return int(match.group(1))

    domain = None
    match = URL_DOMAIN_RE.search(raw)
    if match:
        domain = match.group(1)
    elif raw.startswith("@"):
        domain = raw[1:].strip()
    elif re.fullmatch(r"[a-zA-Z0-9_.]+", raw):
        domain = raw

    if not domain or domain.lower() in {"id", "club", "public", "event"}:
        return None

    try:
        result = await get_api().users.get(user_ids=[domain])
        if result:
            return result[0].id
    except Exception:
        logger.exception("users.get failed for domain %r", domain)

    return None
