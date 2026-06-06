from __future__ import annotations

import asyncio
from typing import Any

from vkbottle.exception_factory.base_exceptions import VKAPIError
from vkbottle.user import Message

from bot.vk_rate import throttle

MessageText = str


async def relay(
    message: Message,
    text: MessageText | None = None,
    *,
    attachment: str | None = None,
    **kwargs: Any,
):
    """Ответ с цитатой (message.reply) — relay для всех команд."""
    last_error: Exception | None = None

    for attempt in range(4):
        try:
            await throttle()
            if message.conversation_message_id:
                return await message.reply(text or "", attachment=attachment, **kwargs)
            return await message.answer(text or "", attachment=attachment, **kwargs)
        except VKAPIError as exc:
            last_error = exc
            code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
            if code == 6 and attempt < 3:
                await asyncio.sleep(1.0 + attempt * 1.5)
                continue
            raise

    if last_error:
        raise last_error
