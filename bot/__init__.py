from vkbottle.api import API
from vkbottle.user import User

from bot.api_context import (
    account_for_api,
    get_api,
    register_api_account,
    set_current_api,
    set_default_api,
)
from bot.config import VkAccount, config
from bot.middleware import ApiContextMiddleware, LogMiddleware
from bot.vk_http import build_vk_api

_self_id_cache: dict[int, int] = {}

apis: list[API] = []
for account in config.accounts:
    api = build_vk_api(account.token, config.ssl_verify)
    register_api_account(api, account)
    apis.append(api)

user = User(api=apis[0])
user.labeler.message_view.register_middleware(LogMiddleware)
user.labeler.message_view.register_middleware(ApiContextMiddleware)
set_default_api(apis[0])

# Обратная совместимость (фоновые задачи идут по apis)
users = [user]


async def resolve_self_id(api: API) -> int:
    account = account_for_api(api)
    if account and account.user_id:
        return account.user_id

    cached = _self_id_cache.get(id(api))
    if cached is not None:
        return cached

    me = (await api.users.get())[0]
    _self_id_cache[id(api)] = me.id
    return me.id


async def get_self_id() -> int:
    return await resolve_self_id(get_api())


def account_label(account: VkAccount) -> str:
    return str(account.user_id or "auto")


__all__ = [
    "account_for_api",
    "account_label",
    "apis",
    "get_api",
    "get_self_id",
    "resolve_self_id",
    "set_current_api",
    "user",
    "users",
]
