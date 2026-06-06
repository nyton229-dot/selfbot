import logging

from vkbottle.user import Message

from bot import user
from bot.prefix_cmds import parse_prefixed_args
from bot.relay import relay
from bot.rules import InfoCommandRule, TrapCatchRule, TrapCommandRule
from bot.trap import disarm_trap, finish_trap, start_trap
from bot.user_info import fetch_friend_status, fetch_user_info, format_user_info
from bot.user_target import resolve_user_id

logger = logging.getLogger(__name__)


@user.on.message(InfoCommandRule(), blocking=True)
async def info_command_handler(message: Message) -> None:
    arg = parse_prefixed_args(message.text or "", "инфо")
    if arg is None:
        return

    user_id = await resolve_user_id(message, arg)
    if not user_id:
        await relay(
            message,
            "Укажи пользователя: reply, @упоминание, ссылку vk.com/id… или vk.com/domain",
        )
        return

    profile = await fetch_user_info(user_id)
    if not profile:
        await relay(message, "Не удалось получить информацию о пользователе.")
        return

    friend_status = await fetch_friend_status(user_id)
    await relay(message, format_user_info(profile, friend_status=friend_status))


@user.on.message(TrapCommandRule(), blocking=True)
async def trap_command_handler(message: Message) -> None:
    peer_id = message.peer_id
    if not peer_id:
        return

    try:
        await start_trap(peer_id)
        logger.info("Trap started in peer=%s", peer_id)
    except Exception:
        logger.exception("Trap start failed")
        await relay(message, "Ловушка: не удалось отправить картинки.")


@user.on.message(TrapCatchRule(), blocking=True)
async def trap_catch_handler(message: Message) -> None:
    peer_id = message.peer_id
    if not peer_id:
        return

    try:
        await finish_trap(peer_id)
        logger.info("Trap caught message from %s in peer=%s", message.from_id, peer_id)
    except Exception:
        logger.exception("Trap finish failed")
        disarm_trap(peer_id)
