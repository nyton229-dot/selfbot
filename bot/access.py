import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ACCESS_FILE = Path(__file__).resolve().parent.parent / "data" / "access.json"


def _load() -> dict[str, dict[str, int]]:
    if not ACCESS_FILE.is_file():
        return {}
    try:
        raw = json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load access file: %s", exc)
        return {}

    result: dict[str, dict[str, int]] = {}
    for peer_key, users in raw.items():
        if not isinstance(users, dict):
            continue
        peer_bucket: dict[str, int] = {}
        for user_key, count in users.items():
            try:
                value = int(count)
            except (TypeError, ValueError):
                continue
            if value > 0:
                peer_bucket[str(user_key)] = value
        if peer_bucket:
            result[str(peer_key)] = peer_bucket
    return result


def _save(data: dict[str, dict[str, int]]) -> None:
    ACCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACCESS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _peer_key(peer_id: int) -> str:
    return str(peer_id)


def _user_key(user_id: int) -> str:
    return str(user_id)


def grant(peer_id: int, user_id: int, count: int) -> int:
    data = _load()
    peer_bucket = data.setdefault(_peer_key(peer_id), {})
    peer_bucket[_user_key(user_id)] = count
    _save(data)
    logger.info("Access granted: peer=%s user=%s count=%s", peer_id, user_id, count)
    return count


def revoke(peer_id: int, user_id: int) -> bool:
    data = _load()
    peer_bucket = data.get(_peer_key(peer_id), {})
    if _user_key(user_id) not in peer_bucket:
        return False
    del peer_bucket[_user_key(user_id)]
    if not peer_bucket:
        data.pop(_peer_key(peer_id), None)
    _save(data)
    logger.info("Access revoked: peer=%s user=%s", peer_id, user_id)
    return True


def get_remaining(peer_id: int, user_id: int) -> int:
    data = _load()
    return data.get(_peer_key(peer_id), {}).get(_user_key(user_id), 0)


def consume(peer_id: int, user_id: int) -> int:
    data = _load()
    peer_bucket = data.get(_peer_key(peer_id), {})
    user_key = _user_key(user_id)
    remaining = peer_bucket.get(user_key, 0)
    if remaining <= 0:
        return 0

    remaining -= 1
    if remaining <= 0:
        peer_bucket.pop(user_key, None)
        if not peer_bucket:
            data.pop(_peer_key(peer_id), None)
    else:
        peer_bucket[user_key] = remaining
    _save(data)
    return remaining
