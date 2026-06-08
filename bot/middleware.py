import logging

from vkbottle.dispatch.middlewares import BaseMiddleware
from vkbottle.user import Message

from bot.api_context import set_current_api

logger = logging.getLogger(__name__)


class LogMiddleware(BaseMiddleware[Message]):
    async def pre(self) -> None:
        msg = self.event
        logger.info(
            "VK incoming: from_id=%s peer_id=%s out=%s text=%r",
            msg.from_id,
            msg.peer_id,
            getattr(msg, "out", None),
            msg.text,
        )


class ApiContextMiddleware(BaseMiddleware[Message]):
    async def pre(self) -> None:
        set_current_api(self.event.ctx_api)

    async def post(self) -> None:
        set_current_api(None)
