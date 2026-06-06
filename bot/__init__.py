from vkbottle.user import User

from bot.config import config
from bot.middleware import LogMiddleware
from bot.vk_http import build_vk_api

user = User(api=build_vk_api(config.vk_token, config.ssl_verify))
user.labeler.message_view.register_middleware(LogMiddleware)

_self_id: int | None = None


async def get_self_id() -> int:
    global _self_id
    if config.vk_user_id:
        return config.vk_user_id
    if _self_id is None:
        me = (await user.api.users.get())[0]
        _self_id = me.id
    return _self_id
