import logging

from vkbottle_types.objects import UsersFields, UsersUserFull

from bot import get_api

logger = logging.getLogger(__name__)

INFO_FIELDS = [
    UsersFields.ONLINE,
    UsersFields.LAST_SEEN,
    UsersFields.ONLINE_INFO,
    UsersFields.SEX,
    UsersFields.BDATE,
    UsersFields.CITY,
    UsersFields.HOME_TOWN,
    UsersFields.STATUS,
    UsersFields.DOMAIN,
    UsersFields.VERIFIED,
    UsersFields.FOLLOWERS_COUNT,
    UsersFields.COUNTERS,
    UsersFields.COMMON_COUNT,
    UsersFields.RELATION,
    UsersFields.OCCUPATION,
    UsersFields.CAN_SEND_FRIEND_REQUEST,
    UsersFields.CAN_WRITE_PRIVATE_MESSAGE,
    UsersFields.SITE,
    UsersFields.ABOUT,
    UsersFields.ACTIVITIES,
    UsersFields.INTERESTS,
    UsersFields.PERSONAL,
]

SEX_LABELS = {0: "не указан", 1: "мужской", 2: "женский"}

RELATION_LABELS = {
    0: "не указано",
    1: "не женат/не замужем",
    2: "есть друг/есть подруга",
    3: "помолвлен(а)",
    4: "женат/замужем",
    5: "всё сложно",
    6: "в активном поиске",
    7: "влюблён(а)",
    8: "в гражданском браке",
}

PLATFORM_LABELS = {
    0: "не в сети",
    1: "📱 моб. сайт",
    2: "📱 iPhone",
    3: "📱 iPad",
    4: "📱 Android",
    5: "📱 Windows Phone",
    6: "💻 Windows",
    7: "💻 веб",
    8: "💻 веб",
    9: "📱 VK",
}

ONLINE_APP_LABELS = {
    2274003: "📱 Android",
    3140623: "📱 iPhone",
    3697615: "📱 iPad",
    5027722: "💻 Windows",
    6287487: "📱 VK Me",
}

FRIEND_STATUS_LABELS = {
    0: "не в друзьях",
    1: "друзья",
    2: "заявка отправлена",
    3: "хочет добавить в друзья",
}


async def fetch_user_info(user_id: int) -> UsersUserFull | None:
    try:
        result = await get_api().users.get(user_ids=[user_id], fields=INFO_FIELDS)
        return result[0] if result else None
    except Exception:
        logger.exception("users.get info failed for %s", user_id)
        return None


async def fetch_friend_status(user_id: int) -> str | None:
    try:
        result = await get_api().friends.are_friends(user_ids=[user_id])
        if not result:
            return None
        status = result[0].friend_status
        if status is None:
            return None
        return FRIEND_STATUS_LABELS.get(status, str(status))
    except Exception:
        logger.warning("friends.areFriends failed for %s", user_id)
        return None


def _nick(profile: UsersUserFull) -> str:
    domain = getattr(profile, "domain", None)
    if domain:
        return f"@{domain}"
    return f"{profile.first_name} {profile.last_name}".strip()


def _fmt_place(obj) -> str | None:
    if not obj:
        return None
    title = getattr(obj, "title", None)
    return str(title) if title else None


def _is_user_online(profile: UsersUserFull) -> bool:
    online = getattr(profile, "online", None)
    if online in (True, 1):
        return True

    online_info = getattr(profile, "online_info", None)
    if online_info and getattr(online_info, "is_online", None) in (True, 1):
        return True

    return False


def _resolve_device(profile: UsersUserFull) -> str | None:
    last_seen = getattr(profile, "last_seen", None)
    platform_id = getattr(last_seen, "platform", None) if last_seen else None
    if platform_id:
        return PLATFORM_LABELS.get(platform_id, f"📱 устройство {platform_id}")

    if not _is_user_online(profile):
        return None

    online_info = getattr(profile, "online_info", None)
    app_id = getattr(profile, "online_app", None) or (
        getattr(online_info, "app_id", None) if online_info else None
    )
    if app_id and app_id in ONLINE_APP_LABELS:
        return ONLINE_APP_LABELS[app_id]

    is_mobile = getattr(profile, "online_mobile", None)
    if is_mobile is None and online_info:
        is_mobile = getattr(online_info, "is_mobile", None)

    if is_mobile is True:
        return "📱 телефон"
    if is_mobile is False:
        return "💻 ПК"
    if app_id:
        return f"📱 приложение {app_id}"
    return None


def _fmt_online(profile: UsersUserFull) -> str:
    if _is_user_online(profile):
        device = _resolve_device(profile)
        if device:
            return f"🟢 в сети · {device}"
        return "🟢 в сети"
    return "⚫ не в сети"


def _short_counters(profile: UsersUserFull) -> str | None:
    counters = getattr(profile, "counters", None)
    if not counters:
        return None

    chunks: list[str] = []
    for attr, emoji in (
        ("friends", "👥"),
        ("followers", "📢"),
        ("photos", "🖼"),
    ):
        value = getattr(counters, attr, None)
        if value is not None:
            chunks.append(f"{emoji}{value}")
    return " · ".join(chunks) if chunks else None


def format_user_info(profile: UsersUserFull, *, friend_status: str | None = None) -> str:
    nick = _nick(profile)

    if getattr(profile, "deactivated", None):
        return f"👤 {nick}\n❌ аккаунт {profile.deactivated}"

    lines = [f"👤 {nick}"]

    if getattr(profile, "verified", None):
        lines[0] += " ✔️"

    lines.append(_fmt_online(profile))

    meta: list[str] = []
    sex = SEX_LABELS.get(getattr(profile, "sex", None))
    if sex and sex != "не указан":
        meta.append("♂️" if getattr(profile, "sex", None) == 1 else "♀️")

    bdate = getattr(profile, "bdate", None)
    if bdate:
        meta.append(f"🎂 {bdate}")

    city = _fmt_place(getattr(profile, "city", None))
    if city:
        meta.append(f"📍 {city}")

    if meta:
        lines.append(" · ".join(meta))

    relation = RELATION_LABELS.get(getattr(profile, "relation", None))
    if relation and relation != "не указано":
        lines.append(f"💍 {relation}")

    if friend_status:
        emoji = {"друзья": "🤝", "заявка отправлена": "📤", "хочет добавить в друзья": "📥"}.get(
            friend_status, "👤"
        )
        lines.append(f"{emoji} {friend_status}")

    common = getattr(profile, "common_count", None)
    if common:
        lines.append(f"🫂 общих друзей: {common}")

    counters = _short_counters(profile)
    if counters:
        lines.append(counters)

    flags: list[str] = []
    if getattr(profile, "is_closed", None):
        flags.append("🔒 закрыт")
    if getattr(profile, "can_access_closed", None):
        flags.append("🔓 доступ есть")
    if getattr(profile, "can_write_private_message", None):
        flags.append("💬 в ЛС ок")
    if getattr(profile, "can_send_friend_request", None):
        flags.append("➕ в друзья ок")
    if flags:
        lines.append(" · ".join(flags))

    status = getattr(profile, "status", None)
    if status:
        short = status if len(status) <= 60 else status[:57] + "..."
        lines.append(f"💬 {short}")

    return "\n".join(lines)
