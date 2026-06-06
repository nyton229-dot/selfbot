import logging
import re

from vkbottle.user import Message
from vkbottle_types.events.user_events import ChatInfoEdit, FriendAction
from vkbottle_types.events.enums import UserEventType
from vkbottle_types.events.objects.user_event_objects import ActionType

from bot import get_self_id, user
from bot.features import get_state
from bot.rules import IncomingAnyRule
logger = logging.getLogger(__name__)

MASS_PUSH_RE = re.compile(
    r"@(?:all|online|everyone|все|всe|online)|\[all\||@\[",
    re.IGNORECASE,
)
_self_removed_friends: set[int] = set()


@user.on.raw_event(UserEventType.FRIEND_ACTION, FriendAction)
async def friend_action_handler(event: FriendAction) -> None:
    obj = event.object
    if not obj or not obj.user_id:
        return
    if obj.action_type == ActionType.REMOVE_OR_CANCEL:
        _self_removed_friends.add(obj.user_id)


@user.on.raw_event(UserEventType.CHAT_INFO_EDIT, ChatInfoEdit)
async def chat_info_handler(event: ChatInfoEdit) -> None:
    if not get_state().auto_leave_chat:
        return

    obj = event.object
    if not obj or obj.type_id is None or obj.peer_id is None:
        return

    self_id = await get_self_id()
    info = obj.info

    if obj.type_id == 6 and info == self_id:
        await _leave_chat(obj.peer_id)
        return

    if obj.type_id in {12, 18} and info in {self_id, 0, 1, 2, 3}:
        if obj.type_id == 18 and info == self_id:
            await _leave_chat(obj.peer_id)


async def _leave_chat(peer_id: int) -> None:
    if peer_id < 2000000000:
        return
    chat_id = peer_id - 2000000000
    self_id = await get_self_id()
    try:
        await user.api.messages.remove_chat_user(chat_id=chat_id, user_id=self_id)
        logger.info("Auto-left chat %s", chat_id)
    except Exception:
        logger.exception("Auto-leave failed for chat %s", chat_id)


@user.on.message(IncomingAnyRule())
async def push_delete_handler(message: Message) -> None:
    state = get_state()
    if not state.delete_pushes and not state.delete_mass_pushes:
        return

    text = message.text or ""
    self_id = await get_self_id()
    delete = False

    if state.delete_mass_pushes and MASS_PUSH_RE.search(text):
        delete = True

    if state.delete_pushes and not delete:
        if f"[id{self_id}|" in text or f"[id{abs(self_id)}|" in text:
            delete = True
        elif message.reply_message and message.reply_message.from_id == self_id:
            delete = True

    if not delete:
        return

    cmid = message.conversation_message_id
    if not cmid:
        return

    try:
        await user.api.messages.delete(
            peer_id=message.peer_id,
            cmids=[cmid],
            delete_for_all=False,
        )
        logger.info("Deleted push message peer=%s cmid=%s", message.peer_id, cmid)
    except Exception:
        logger.exception("Push delete failed")
