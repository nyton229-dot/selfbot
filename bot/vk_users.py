import logging

from bot import get_api

logger = logging.getLogger(__name__)

_name_cache: dict[int, str] = {}


async def get_display_name(user_id: int) -> str:
    if user_id in _name_cache:
        return _name_cache[user_id]

    try:
        result = await get_api().users.get(user_ids=[user_id])
        if result:
            profile = result[0]
            name = f"{profile.first_name} {profile.last_name}".strip()
            if name:
                _name_cache[user_id] = name
                return name
    except Exception as exc:
        logger.warning("users.get failed for %s: %s", user_id, exc)

    return "пользователь"
