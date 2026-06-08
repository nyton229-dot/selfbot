import asyncio
import logging

from vkbottle.user import Message

from bot import get_api, get_self_id

logger = logging.getLogger(__name__)


async def _fetch_reply_message_from_api(message: Message):
    peer_id = message.peer_id
    if not peer_id:
        return None

    try:
        if message.id:
            result = await get_api().messages.get_by_id(
                peer_id=peer_id,
                message_ids=[message.id],
            )
        elif message.conversation_message_id:
            result = await get_api().messages.get_by_id(
                peer_id=peer_id,
                cmids=[message.conversation_message_id],
            )
        else:
            return None
    except Exception as exc:
        logger.warning("messages.getById for reply failed: %s", exc)
        return None

    if not result.items:
        return None

    return getattr(result.items[0], "reply_message", None)


async def resolve_reply_message(message: Message):
    reply = getattr(message, "reply_message", None)
    if reply:
        return reply

    reply = await _fetch_reply_message_from_api(message)
    if reply:
        return reply

    await asyncio.sleep(0.5)
    return await _fetch_reply_message_from_api(message)


async def _resolve_target_from_reply(reply) -> int | None:
    from_id = getattr(reply, "from_id", None)
    if not from_id:
        return None

    self_id = await get_self_id()
    if from_id != self_id:
        return from_id

    nested = getattr(reply, "reply_message", None)
    nested_id = getattr(nested, "from_id", None) if nested else None
    if nested_id and nested_id != self_id:
        return nested_id

    return None


async def resolve_reply_from_id(message: Message) -> int | None:
    reply = getattr(message, "reply_message", None)
    if reply:
        target_id = await _resolve_target_from_reply(reply)
        if target_id:
            return target_id

    reply = await _fetch_reply_message_from_api(message)
    if reply:
        target_id = await _resolve_target_from_reply(reply)
        if target_id:
            return target_id

    await asyncio.sleep(0.5)
    reply = await _fetch_reply_message_from_api(message)
    if reply:
        return await _resolve_target_from_reply(reply)
    return None
