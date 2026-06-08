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

users: list[User] = []
for account in config.accounts:
    vk_user = User(api=build_vk_api(account.token, config.ssl_verify))
    register_api_account(vk_user.api, account)
    vk_user.labeler.message_view.register_middleware(LogMiddleware)
    vk_user.labeler.message_view.register_middleware(ApiContextMiddleware)
    users.append(vk_user)

user = users[0]
set_default_api(users[0].api)


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


def mirror_accounts() -> None:
    """Копирует обработчики первого аккаунта на остальные."""
    if len(users) <= 1:
        return

    primary = users[0]
    for extra in users[1:]:
        extra.loop_wrapper = primary.loop_wrapper
        extra.labeler.load(primary.labeler)
        extra.labeler.message_view.register_middleware(LogMiddleware)
        extra.labeler.message_view.register_middleware(ApiContextMiddleware)


def account_label(account: VkAccount) -> str:
    return str(account.user_id or "auto")


__all__ = [
    "account_for_api",
    "account_label",
    "get_api",
    "get_self_id",
    "mirror_accounts",
    "resolve_self_id",
    "set_current_api",
    "user",
    "users",
]
