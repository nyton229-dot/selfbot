from contextvars import ContextVar
from typing import TYPE_CHECKING

from vkbottle.api import API

if TYPE_CHECKING:
    from bot.config import VkAccount

_current_api: ContextVar[API | None] = ContextVar("current_api", default=None)
_default_api: API | None = None
_api_accounts: dict[int, "VkAccount"] = {}


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


def register_api_account(api: API, account: "VkAccount") -> None:
    _api_accounts[id(api)] = account


def account_for_api(api: API) -> "VkAccount | None":
    return _api_accounts.get(id(api))
