import logging



from vkbottle.user import Message



from bot import get_self_id, user

from bot import access as access_store

from bot.ai import generate_reply

from bot.config import config

from bot.context import get_context_prefix, save_exchange

from bot.helpers import (

    extract_ai_query,

    has_ai_command,

    is_dov_grant,

    is_dov_revoke,

)

from bot.media import collect_media, has_recognizable_media, should_collect_media
from bot.replies import resolve_reply_from_id
from bot.relay import relay
from bot.rules import DovAdminRule, IncomingMessageRule
from bot.vk_users import get_display_name



logger = logging.getLogger(__name__)



PREFIX = config.ai_prefix

AI_ERROR = "Артем сейчас не может ответить. Попробуй чуть позже."

MEDIA_ERROR = (

    "Не удалось получить кадр из видео. "

    "Попробуй отправить видео ещё раз или ответь на мой предыдущий разбор."

)





@user.on.message(DovAdminRule())

async def dov_admin_handler(message: Message) -> None:

    try:

        target_id = await resolve_reply_from_id(message)

        if not target_id:

            await relay(message,
                "Ответь (reply) на сообщение человека, которому выдаёшь или забираешь доступ."
            )

            return



        self_id = await get_self_id()

        name = await get_display_name(target_id)

        if target_id == self_id:

            await relay(message, "Тебе доступ не нужен — ты владелец, Артем отвечает тебе всегда.")

            return



        grant_count = is_dov_grant(message.text)

        if grant_count is not None:

            if grant_count <= 0:

                await relay(message, "Укажи число больше 0, например: /+дов 5")

                return

            access_store.grant(message.peer_id, target_id, grant_count)

            await relay(message,
                f"Выдал {name} доступ: {grant_count} запросов «{PREFIX}» в этом чате."
            )

            return



        if is_dov_revoke(message.text):

            if access_store.revoke(message.peer_id, target_id):

                await relay(message, f"Забрал доступ у {name} в этом чате.")

            else:

                await relay(message, f"У {name} не было доступа в этом чате.")

    except Exception:

        logger.exception("Dov admin handler error")

        raise





@user.on.message(IncomingMessageRule())

async def message_handler(message: Message) -> None:

    try:

        user_text = (message.text or "").strip()

        if not user_text:

            return



        if not has_ai_command(user_text, PREFIX):

            return



        self_id = await get_self_id()

        sender_id = message.from_id or self_id

        is_owner = sender_id == self_id



        if not is_owner:

            remaining = access_store.get_remaining(message.peer_id, sender_id)

            if remaining <= 0:

                logger.info(

                    "AI denied: no access peer=%s user=%s",

                    message.peer_id,

                    sender_id,

                )

                return



        ai_query = extract_ai_query(user_text, PREFIX)

        has_media = has_recognizable_media(message)

        if not ai_query and not has_media:
            if is_owner:
                await relay(
                    message,
                    f"Напиши вопрос после «{PREFIX}», например: {PREFIX} привет",
                )
            return

        if not config.ai_enabled:
            if is_owner:
                await relay(
                    message,
                    "ИИ выключен: на Bothost добавь AI_API_KEY и перезапусти бота.",
                )
            return

        query_text = ai_query or ""

        collect = should_collect_media(message, query_text)

        media = await collect_media(message, query_text) if collect else None



        if (

            collect

            and media

            and not media.has_images

            and not media.audio_transcripts

        ):

            logger.warning("Media present but frame/audio extraction failed")

            await relay(message, MEDIA_ERROR)

            return



        prompt = get_context_prefix(message.peer_id, query_text) + query_text

        logger.info(
            "AI request: %r from=%s owner=%s ai=%s key_len=%d (images=%d transcripts=%d followup=%s)",
            query_text,
            sender_id,
            is_owner,
            config.ai_enabled,
            len(config.ai_api_key),
            len(media.image_data_urls) if media else 0,
            len(media.audio_transcripts) if media else 0,
            bool(get_context_prefix(message.peer_id, query_text)),
        )

        ai_reply = await generate_reply(prompt, media)

        if ai_reply:

            await relay(message, ai_reply)

            save_exchange(message.peer_id, query_text, ai_reply)

            if not is_owner:

                left = access_store.consume(message.peer_id, sender_id)

                logger.info("Access consumed: user=%s left=%s", sender_id, left)

            logger.info("AI reply sent")

            return



        logger.warning("AI reply failed (enabled=%s)", config.ai_enabled)
        if is_owner and not config.ai_enabled:
            await relay(
                message,
                "ИИ выключен: добавь AI_API_KEY на Bothost и перезапусти бота.",
            )
        else:
            await relay(message, AI_ERROR)

    except Exception:

        logger.exception("Handler error")

        raise


