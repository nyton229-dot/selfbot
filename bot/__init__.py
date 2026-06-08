from vkbottle.user import User

from bot.api_context import get_api, set_current_api, set_default_api
from bot.config import VkAccount, config
from bot.middleware import ApiContextMiddleware, LogMiddleware
from bot.vk_http import build_vk_api

_api_accounts: dict[int, VkAccount] = {}
_self_id_cache: dict[int, int] = {}

users: list[User] = []
for account in config.accounts:
    vk_user = User(api=build_vk_api(account.token, config.ssl_verify))
    _api_accounts[id(vk_user.api)] = account
    vk_user.labeler.message_view.register_middleware(LogMiddleware)
    vk_user.labeler.message_view.register_middleware(ApiContextMiddleware)
    users.append(vk_user)

user = users[0]
set_default_api(users[0].api)


async def get_self_id() -> int:
    api = get_api()
    account = _api_accounts.get(id(api))
    if account and account.user_id:
        return account.user_id

    cached = _self_id_cache.get(id(api))
    if cached is not None:
        return cached

    me = (await api.users.get())[0]
    _self_id_cache[id(api)] = me.id
    return me.id


def mirror_accounts() -> None:
    """Копирует обработчики первого аккаунта на остальные."""
    if len(users) <= 1:
        return

    primary = users[0]
    for extra in users[1:]:
        extra.loop_wrapper = primary.loop_wrapper
        extra.labeler.load(primary.labeler)


def account_label(account: VkAccount) -> str:
    return str(account.user_id or "auto")


__all__ = [
    "account_label",
    "get_api",
    "get_self_id",
    "mirror_accounts",
    "set_current_api",
    "user",
    "users",
]
