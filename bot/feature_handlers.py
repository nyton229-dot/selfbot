import logging

from vkbottle.user import Message

from bot import get_api, get_self_id, user
from bot.cover_updater import update_profile_cover
from bot.feature_tasks import _set_offline, _set_online
from bot.features import (
    TOGGLE_LABELS,
    build_help,
    build_menu,
    get_state,
    parse_deleter_command,
    resolve_nd_command,
    resolve_nd_deleter_trigger,
    resolve_nd_edit_text,
    resolve_toggle_command,
    resolve_nd_prefix,
    set_command_prefix,
    set_deleter_edit_text,
    set_deleter_trigger,
    set_feature,
    toggle,
)
from bot.relay import relay
from bot.rules import (
    DeleterRule,
    FeatureToggleRule,
    NdConfigRule,
    NdMenuRule,
    RepeaterRule,
)

logger = logging.getLogger(__name__)


@user.on.message(NdMenuRule(), blocking=True)
async def nd_menu_handler(message: Message) -> None:
    text = (message.text or "").strip().lower()
    if text == "нд помощь":
        await relay(message,build_help())
    else:
        await relay(message,build_menu())


@user.on.message(NdConfigRule(), blocking=True)
async def nd_config_handler(message: Message) -> None:
    text = message.text or ""

    trigger = resolve_nd_deleter_trigger(text)
    if trigger is not None:
        set_deleter_trigger(trigger)
        await relay(message,f"Команда удалялки: «{trigger}»")
        return

    edit_text = resolve_nd_edit_text(text)
    if edit_text is not None:
        set_deleter_edit_text(edit_text)
        await relay(message,f"Текст умной удалялки: «{edit_text}»")
        return

    cmd_prefix = resolve_nd_prefix(text)
    if cmd_prefix is not None:
        set_command_prefix(cmd_prefix)
        await relay(message,f"Префикс команд: «{cmd_prefix}»")


@user.on.message(FeatureToggleRule(), blocking=True)
async def feature_toggle_handler(message: Message) -> None:
    text = message.text or ""
    parsed = resolve_nd_command(text)
    if parsed:
        field, enabled = parsed
        set_feature(field, enabled)
    else:
        field = resolve_toggle_command(text)
        if not field:
            return
        enabled = toggle(field)
    label = TOGGLE_LABELS.get(field, field)
    status = "включено" if enabled else "выключено"

    if field == "eternal_online" and enabled:
        await _set_online()
    elif field == "eternal_offline" and enabled:
        await _set_offline()
    elif field == "dynamic_cover" and enabled:
        try:
            await update_profile_cover()
        except Exception:
            logger.exception("Immediate cover update failed")

    await relay(message,f"{label}: {status}")


@user.on.message(RepeaterRule(), blocking=True)
async def repeater_handler(message: Message) -> None:
    state = get_state()
    text = message.text or ""
    prefix = state.repeater_prefix
    payload = text[len(prefix) :].lstrip()
    if not payload:
        return

    await relay(message,payload)
    logger.info("Repeater: %r", payload[:80])


@user.on.message(DeleterRule(), blocking=True)
async def deleter_handler(message: Message) -> None:
    state = get_state()
    count = parse_deleter_command(message.text or "")
    if count is None:
        return

    reply_cmid = await _resolve_reply_cmid(message)
    if reply_cmid and state.smart_deleter:
        await _smart_delete(message, reply_cmid)
        return

    if not state.deleter:
        if state.smart_deleter:
            await relay(message,"Умная удалялка: ответь (reply) на сообщение.")
        return

    deleted = await _delete_own_messages(message.peer_id, count)
    logger.info("Deleter removed %s own messages in peer=%s", deleted, message.peer_id)


async def _smart_delete(message: Message, reply_cmid: int) -> None:
    state = get_state()
    try:
        await get_api().messages.edit(
            peer_id=message.peer_id,
            cmid=reply_cmid,
            message=state.deleter_edit_text,
        )
        if message.conversation_message_id:
            await get_api().messages.delete(
                peer_id=message.peer_id,
                cmids=[message.conversation_message_id],
                delete_for_all=False,
            )
        logger.info("Smart deleter: edited cmid=%s", reply_cmid)
    except Exception:
        logger.exception("Smart deleter failed")


async def _delete_own_messages(peer_id: int | None, count: int) -> int:
    if not peer_id:
        return 0

    self_id = await get_self_id()
    try:
        history = await get_api().messages.get_history(
            peer_id=peer_id,
            count=min(200, count * 10),
        )
    except Exception:
        logger.exception("getHistory failed")
        return 0

    cmids: list[int] = []
    for msg in history.items or []:
        if msg.from_id != self_id:
            continue
        cmid = getattr(msg, "conversation_message_id", None)
        if not cmid:
            continue
        cmids.append(cmid)
        if len(cmids) >= count:
            break

    if not cmids:
        return 0

    try:
        await get_api().messages.delete(
            peer_id=peer_id,
            cmids=cmids,
            delete_for_all=False,
        )
    except Exception:
        logger.exception("messages.delete failed")
        return 0

    return len(cmids)


async def _resolve_reply_cmid(message: Message) -> int | None:
    reply = message.reply_message
    if reply and reply.conversation_message_id:
        return reply.conversation_message_id

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
    except Exception:
        return None

    if not result.items:
        return None

    reply = getattr(result.items[0], "reply_message", None)
    if reply and reply.conversation_message_id:
        return reply.conversation_message_id
    return None
