import logging

from vkbottle.user import Message

from bot import get_self_id, user
from bot.prefix_cmds import parse_prefixed_args
from bot.relay import relay
from bot.quote_card import fetch_author_avatar, generate_quote_card, message_date_to_timestamp
from bot.replies import resolve_reply_message
from bot.rules import InfoCommandRule, QuoteCommandRule, TrapCatchRule, TrapCommandRule
from bot.vk_photo import upload_message_photo
from bot.vk_users import get_display_name
from bot.trap import disarm_trap, finish_trap, start_trap
from bot.user_info import fetch_friend_status, fetch_user_info, format_user_info
from bot.user_target import resolve_user_id

logger = logging.getLogger(__name__)


@user.on.message(QuoteCommandRule(), blocking=True)
async def quote_command_handler(message: Message) -> None:
    if parse_prefixed_args(message.text or "", "цит") is None:
        return

    reply = await resolve_reply_message(message)
    if not reply:
        await relay(message, "Ответь (reply) на сообщение, из которого нужно сделать цитату.")
        return

    quote_text = (reply.text or "").strip()
    if not quote_text:
        await relay(message, "В сообщении нет текста для цитаты.")
        return

    author_id = getattr(reply, "from_id", None)
    if not author_id:
        await relay(message, "Не удалось определить автора сообщения.")
        return

    try:
        author_name = await get_display_name(author_id)
        avatar_bytes = await fetch_author_avatar(author_id)
        if not avatar_bytes:
            logger.warning("Quote card: avatar missing for author_id=%s", author_id)
        self_id = await get_self_id()
        image_bytes = generate_quote_card(
            author_name=author_name,
            quote_text=quote_text,
            message_date=message_date_to_timestamp(getattr(reply, "date", 0)),
            avatar_bytes=avatar_bytes,
            footer_avatar_bytes=await fetch_author_avatar(self_id),
        )
        attachment = await upload_message_photo(message.peer_id, image_bytes, "quote.jpg")
        await relay(message, attachment=attachment)
        logger.info("Quote card sent for author=%s peer=%s", author_id, message.peer_id)
    except Exception:
        logger.exception("Quote command failed")
        await relay(message, "Не удалось сделать цитату.")


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
