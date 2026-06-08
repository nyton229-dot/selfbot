from vkbottle.dispatch.rules.base import ABCRule

from vkbottle.user import Message



from bot import get_self_id

from bot.features import get_state, is_feature_command, is_nd_config_command, parse_deleter_command
from bot.trap import match_prefixed_command, should_catch_trap_message
from bot.prefix_cmds import parse_prefixed_args
from bot.voices import parse_voice_command





class OwnerOutgoingRule(ABCRule[Message]):

    """Только исходящие сообщения владельца."""



    async def check(self, event: Message) -> bool:

        self_id = await get_self_id()

        out = int(getattr(event, "out", 0) or 0)

        return out == 1 and event.from_id == self_id





class NdMenuRule(ABCRule[Message]):

    async def check(self, event: Message) -> bool:

        if not await OwnerOutgoingRule().check(event):

            return False

        text = (event.text or "").strip().lower()

        return text in {"нд", "нд помощь"}


class InfoCommandRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        if not await OwnerOutgoingRule().check(event):
            return False
        return parse_prefixed_args(event.text or "", "инфо") is not None


class QuoteCommandRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        if not await OwnerOutgoingRule().check(event):
            return False
        return parse_prefixed_args(event.text or "", "цит") is not None


class VoiceCommandRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        if not await OwnerOutgoingRule().check(event):
            return False
        return parse_voice_command(event.text or "") is not None


class TrapCommandRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        if not await OwnerOutgoingRule().check(event):
            return False
        return match_prefixed_command(event.text or "", "ловушка")


class TrapCatchRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        self_id = await get_self_id()
        return should_catch_trap_message(
            peer_id=event.peer_id,
            from_id=event.from_id,
            self_id=self_id,
            text=event.text,
            out=int(getattr(event, "out", 0) or 0),
        )


class NdConfigRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        if not await OwnerOutgoingRule().check(event):
            return False
        return is_nd_config_command(event.text or "")


class FeatureToggleRule(ABCRule[Message]):

    async def check(self, event: Message) -> bool:

        if not await OwnerOutgoingRule().check(event):

            return False

        return is_feature_command(event.text or "")





class RepeaterRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        if not await OwnerOutgoingRule().check(event):
            return False
        state = get_state()
        if not state.repeater:
            return False
        text = event.text or ""
        return text.startswith(state.repeater_prefix) and len(text) > len(state.repeater_prefix)


class DeleterRule(ABCRule[Message]):
    async def check(self, event: Message) -> bool:
        if not await OwnerOutgoingRule().check(event):
            return False
        state = get_state()
        if not state.deleter and not state.smart_deleter:
            return False
        return parse_deleter_command(event.text or "") is not None


class IncomingAnyRule(ABCRule[Message]):

    """Любое входящее сообщение."""



    async def check(self, event: Message) -> bool:

        return int(getattr(event, "out", 0) or 0) == 0





