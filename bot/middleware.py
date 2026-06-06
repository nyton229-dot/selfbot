import logging

from vkbottle.dispatch.middlewares import BaseMiddleware
from vkbottle.user import Message

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
