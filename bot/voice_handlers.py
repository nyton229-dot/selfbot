import logging

from vkbottle.user import Message

from bot import user
from bot.relay import relay
from bot.replies import resolve_reply_message
from bot.rules import VoiceCommandRule
from bot.voices import (
    delete_voice,
    extract_voice_attachment,
    get_voice,
    parse_voice_command,
    save_voice,
)

logger = logging.getLogger(__name__)


@user.on.message(VoiceCommandRule(), blocking=True)
async def voice_command_handler(message: Message) -> None:
    parsed = parse_voice_command(message.text or "")
    if not parsed:
        return

    action, name = parsed
    peer_id = message.peer_id
    if not peer_id:
        return

    if action == "save":
        await _handle_save(message, name)
    elif action == "delete":
        await _handle_delete(message, name)
    elif action == "send":
        await _handle_send(message, name, peer_id)


async def _handle_save(message: Message, name: str) -> None:
    reply = await resolve_reply_message(message)
    if not reply:
        await relay(message, "Ответь (reply) на голосовое сообщение.")
        return

    attachment = extract_voice_attachment(reply)
    if not attachment:
        await relay(message, "В ответе нет голосового сообщения.")
        return

    voices = reply.get_audio_message_attachments() or []
    saved = save_voice(name, voices[0])
    await relay(message, f"ГС сохранено: «{saved.name}»")


async def _handle_delete(message: Message, name: str) -> None:
    if delete_voice(name):
        await relay(message, f"ГС удалено: «{name}»")
    else:
        await relay(message, f"ГС «{name}» не найдено.")


async def _handle_send(message: Message, name: str, peer_id: int) -> None:
    saved = get_voice(name)
    if not saved:
        await relay(message, f"ГС «{name}» не найдено.")
        return

    try:
        await relay(message, attachment=saved.attachment)
        logger.info("Sent saved voice %r in peer=%s", saved.name, peer_id)
    except Exception:
        logger.exception("Failed to send voice %r", saved.name)
        await relay(message, f"Не удалось отправить ГС «{saved.name}».")
