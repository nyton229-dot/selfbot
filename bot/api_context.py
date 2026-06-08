from contextvars import ContextVar

from vkbottle.api import API

_current_api: ContextVar[API | None] = ContextVar("current_api", default=None)
_default_api: API | None = None


def set_default_api(api: API) -> None:
    global _default_api
    _default_api = api


def set_current_api(api: API | None) -> None:
    _current_api.set(api)


def get_api() -> API:
    api = _current_api.get()
    if api is not None:
        return api
    if _default_api is not None:
        return _default_api
    raise RuntimeError("VK API is not initialized")
