import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bot.config import config

logger = logging.getLogger(__name__)

FEATURES_FILE = Path(__file__).resolve().parent.parent / "data" / "features.json"

ON = "✅"
OFF = "❌"
MAX_DELETER_COUNT = 50
DEFAULT_DELETER_COUNT = 10


@dataclass
class FeatureState:
    auto_add_friends: bool = False
    eternal_online: bool = False
    eternal_offline: bool = False
    delete_dogs: bool = False
    auto_unfollow: bool = False
    delete_pushes: bool = False
    delete_mass_pushes: bool = False
    auto_leave_chat: bool = False
    repeater: bool = False
    deleter: bool = False
    smart_deleter: bool = False
    repeater_prefix: str = ".."
    deleter_trigger: str = "дд"
    deleter_edit_text: str = "ахаххаххах я удалил"
    command_prefix: str = "л"
    trap_photo_top: str = ""
    trap_photo_bottom: str = ""
    trap_assets_version: int = 0
    dynamic_cover: bool = False
    _friend_ids: list[int] = field(default_factory=list)

    def icon(self, enabled: bool) -> str:
        return ON if enabled else OFF


def _load_raw() -> dict:
    if not FEATURES_FILE.is_file():
        return {}
    try:
        return json.loads(FEATURES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load features: %s", exc)
        return {}


def load_state() -> FeatureState:
    raw = _load_raw()
    known = {f.name for f in FeatureState.__dataclass_fields__.values()}
    data = {key: raw[key] for key in known if key in raw}
    return FeatureState(**data)


def save_state(state: FeatureState) -> None:
    FEATURES_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEATURES_FILE.write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_state = load_state()


def get_state() -> FeatureState:
    return _state


def _apply_mutual_exclusion(field: str) -> None:
    if field == "eternal_online" and _state.eternal_online:
        _state.eternal_offline = False
    if field == "eternal_offline" and _state.eternal_offline:
        _state.eternal_online = False


def set_feature(field: str, enabled: bool) -> bool:
    global _state
    setattr(_state, field, enabled)
    _apply_mutual_exclusion(field)
    save_state(_state)
    logger.info("Feature %s -> %s", field, enabled)
    return enabled


def toggle(field: str) -> bool:
    global _state
    current = getattr(_state, field)
    return set_feature(field, not current)


def set_friend_ids(ids: list[int]) -> None:
    _state._friend_ids = ids
    save_state(_state)


def get_friend_ids() -> set[int]:
    return set(_state._friend_ids)


TOGGLE_ALIASES: dict[str, str] = {
    "автодобавление": "auto_add_friends",
    "автодобавление в друзья": "auto_add_friends",
    "онлайн": "eternal_online",
    "вечный онлайн": "eternal_online",
    "оффлайн": "eternal_offline",
    "вечный оффлайн": "eternal_offline",
    "удаление собак": "delete_dogs",
    "собаки": "delete_dogs",
    "автоотписка": "auto_unfollow",
    "удаление пушей": "delete_pushes",
    "пуши": "delete_pushes",
    "удаление массовых пушей": "delete_mass_pushes",
    "массовые пуши": "delete_mass_pushes",
    "автовыход": "auto_leave_chat",
    "повторялка": "repeater",
    "удалялка": "deleter",
    "умная удалялка": "smart_deleter",
    "динамическая обложка": "dynamic_cover",
    "обложка": "dynamic_cover",
}

TOGGLE_LABELS: dict[str, str] = {
    "auto_add_friends": "Автодобавление в друзья",
    "eternal_online": "Вечный онлайн",
    "eternal_offline": "Вечный оффлайн (заходил недавно)",
    "delete_dogs": "Автоудаление «собачек»",
    "auto_unfollow": "Автоотписка",
    "delete_pushes": "Удаление пушей",
    "delete_mass_pushes": "Удаление массовых пушей",
    "auto_leave_chat": "Автовыход из бесед",
    "repeater": "Повторялка",
    "deleter": "Удалялка",
    "smart_deleter": "Умная удалялка",
    "dynamic_cover": "Динамическая обложка профиля",
}


def set_deleter_trigger(trigger: str) -> str:
    global _state
    value = trigger.strip()
    if not value:
        raise ValueError("empty trigger")
    _state.deleter_trigger = value
    save_state(_state)
    logger.info("Deleter trigger -> %r", value)
    return value


def set_trap_photo(which: str, attachment: str) -> None:
    global _state
    setattr(_state, f"trap_photo_{which}", attachment)
    save_state(_state)


def set_trap_assets_version(version: int) -> None:
    global _state
    _state.trap_assets_version = version
    save_state(_state)


def set_command_prefix(prefix: str) -> str:
    global _state
    value = prefix.strip()
    if not value:
        raise ValueError("empty prefix")
    _state.command_prefix = value
    save_state(_state)
    logger.info("Command prefix -> %r", value)
    return value


def set_deleter_edit_text(text: str) -> str:
    global _state
    value = text.strip()
    if not value:
        raise ValueError("empty edit text")
    _state.deleter_edit_text = value
    save_state(_state)
    logger.info("Deleter edit text -> %r", value[:80])
    return value


def resolve_nd_deleter_trigger(text: str) -> str | None:
    """«нд удалялка дд» — сменить команду удалялки."""
    raw = (text or "").strip()
    lower = raw.lower()
    prefix = "нд удалялка "
    if not lower.startswith(prefix):
        return None
    payload = raw[len(prefix) :].strip()
    if not payload or payload.lower() in {"вкл", "выкл"}:
        return None
    return payload


def resolve_nd_prefix(text: str) -> str | None:
    """«нд префикс л» — префикс команд (ловушка и др.)."""
    raw = (text or "").strip()
    lower = raw.lower()
    prefix = "нд префикс "
    if not lower.startswith(prefix):
        return None
    payload = raw[len(prefix) :].strip()
    if not payload:
        return None
    return payload


def resolve_nd_edit_text(text: str) -> str | None:
    """«нд редач фраза» — текст для умной удалялки."""
    raw = (text or "").strip()
    lower = raw.lower()
    prefix = "нд редач "
    if not lower.startswith(prefix):
        return None
    payload = raw[len(prefix) :].strip()
    if not payload:
        return None
    return payload


def parse_deleter_command(text: str) -> int | None:
    """«дд» → 10, «дд5» → 5. None если не команда удалялки."""
    trigger = _state.deleter_trigger
    if not trigger:
        return None

    stripped = (text or "").strip()
    pattern = re.compile(rf"^{re.escape(trigger)}(\d+)?$", re.IGNORECASE)
    match = pattern.match(stripped)
    if not match:
        return None

    count = int(match.group(1)) if match.group(1) else DEFAULT_DELETER_COUNT
    return min(max(count, 1), MAX_DELETER_COUNT)


def is_nd_config_command(text: str) -> bool:
    return (
        resolve_nd_deleter_trigger(text) is not None
        or resolve_nd_edit_text(text) is not None
        or resolve_nd_prefix(text) is not None
    )


def _match_feature(text: str) -> str | None:
    normalized = (text or "").strip().lower()
    return TOGGLE_ALIASES.get(normalized)


def resolve_nd_command(text: str) -> tuple[str, bool] | None:
    """«нд вкл онлайн» / «нд выкл пуши» → (field, enabled)."""
    normalized = (text or "").strip().lower()
    parts = normalized.split()
    if len(parts) < 3 or parts[0] != "нд":
        return None
    if parts[1] not in {"вкл", "выкл"}:
        return None

    enabled = parts[1] == "вкл"
    field = _match_feature(" ".join(parts[2:]))
    if not field:
        return None
    return field, enabled


def resolve_toggle_command(text: str) -> str | None:
    return _match_feature(text)


def is_feature_command(text: str) -> bool:
    return resolve_nd_command(text) is not None or resolve_toggle_command(text) is not None


def build_menu() -> str:
    s = get_state()
    lines = [
        "Нд — статус функций",
        "",
        f"{s.icon(s.auto_add_friends)} Автодобавление в друзья",
        f"{s.icon(s.delete_dogs)} Автоудаление «собачек»",
        f"{s.icon(s.auto_leave_chat)} Автовыход из бесед",
        f"{s.icon(s.delete_pushes)} Удаление пушей",
        f"{s.icon(s.eternal_offline)} Вечный оффлайн",
        f"{s.icon(s.eternal_online)} Вечный онлайн",
        f"{s.icon(s.auto_unfollow)} Автоотписка",
        f"{s.icon(s.delete_mass_pushes)} Удаление массовых пушей",
        f"{s.icon(s.repeater)} Повторялка ({s.repeater_prefix})",
        f"{s.icon(s.deleter)} Удалялка ({s.deleter_trigger})",
        f"{s.icon(s.smart_deleter)} Умная удалялка → «{s.deleter_edit_text[:30]}»",
        f"{s.icon(s.dynamic_cover)} Динамическая обложка профиля",
        "",
        f"Префикс команд: {ON} {s.command_prefix}",
        f"Префикс ИИ: {ON} {config.ai_prefix}",
        "",
        "Список команд — «нд помощь»",
    ]
    return "\n".join(lines)


def build_help() -> str:
    return """\
Нд помощь — описание команд

автодобавление — если кто-то добавляет в друзья, добавляешь в ответ.
онлайн — вечный онлайн в сети.
оффлайн — статус «заходил недавно».
удаление собак / собаки — удаляет заблокированных/удалённых из друзей.
автоотписка — отписка, если тебя удалили из друзей.
удаление пушей / пуши — удаляет упоминания тебя (только у тебя).
удаление массовых пушей / массовые пуши — удаляет @all и аналоги.
автовыход — выход из бесед, куда тебя добавили.
повторялка — дублирует текст после «..»
динамическая обложка / обложка — обложка профиля, время по МСК, обновление каждую минуту.

удалялка — удаляет твои сообщения по команде (по умолчанию «дд»).
«дд» — удалит 10 последних, «дд5» — 5, «дд20» — 20 (макс. 50).
умная удалялка — ответь командой на сообщение: сначала редактирует, потом удаляет команду.
нд удалялка <слово> — сменить команду удалялки.
нд редач <фраза> — текст, на который умная удалялка редактирует сообщение.

нд вкл <функция> — включить, нд выкл <функция> — выключить.
Например: «нд вкл онлайн», «нд выкл пуши», «нд вкл удаление собак».

л инфо — расширенная инфа о пользователе (reply / @упом / ссылка).
л ловушка — прикол-ловушка: кидает верх руки, ждёт ответ, потом низ.
л +гс <имя> — сохранить ГС (reply на голосовое).
л -гс <имя> — удалить сохранённое ГС.
л гс <имя> — отправить сохранённое ГС.
нд префикс <буква> — сменить префикс команд (по умолчанию «л»).

Только владелец (исходящие сообщения).
/+дов /-дов — доступ к ИИ (ответом на сообщение)."""
