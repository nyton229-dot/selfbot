import re

from vkbottle.user import Message

START_TEXTS = frozenset({"/start", "начать", "start"})

FOLLOWUP_QUERIES = frozenset(
    {
        "обоснуй",
        "подробнее",
        "почему",
        "объясни",
        "разверни",
        "уточни",
        "докажи",
        "аргументируй",
        "поясни",
        "а почему",
        "а как",
        "и что",
        "ну и",
    }
)

DOV_GRANT_RE = re.compile(r"^/\+дов\s*(\d+)\s*$", re.IGNORECASE)
DOV_REVOKE_RE = re.compile(r"^/-дов\s*$", re.IGNORECASE)


def is_chat(message: Message) -> bool:
    return message.peer_id != message.from_id


def is_start_text(text: str | None) -> bool:
    return (text or "").strip().lower() in START_TEXTS


def is_dov_grant(text: str | None) -> int | None:
    match = DOV_GRANT_RE.match((text or "").strip())
    if not match:
        return None
    return int(match.group(1))


def is_dov_revoke(text: str | None) -> bool:
    return bool(DOV_REVOKE_RE.match((text or "").strip()))


def is_dov_admin_command(text: str | None) -> bool:
    stripped = (text or "").strip()
    return is_dov_grant(stripped) is not None or is_dov_revoke(stripped)


def has_ai_command(text: str | None, prefix: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or not prefix:
        return False
    return stripped.lower().startswith(prefix.lower())


def is_followup_query(query: str) -> bool:
    normalized = (query or "").lower().strip().strip("?!.")
    if not normalized:
        return False
    if normalized in FOLLOWUP_QUERIES:
        return True
    return any(normalized.startswith(word) for word in FOLLOWUP_QUERIES)


def extract_ai_query(text: str | None, prefix: str) -> str | None:
    if not has_ai_command(text, prefix):
        return None

    stripped = (text or "").strip()
    return stripped[len(prefix) :].lstrip(" ,:—-")
