import re

from bot.features import get_state


def parse_prefixed_args(text: str, command: str) -> str | None:
    """None — не команда; '' — без аргументов; иначе строка аргументов."""
    state = get_state()
    prefix = re.escape(state.command_prefix.strip())
    cmd = re.escape(command)
    raw = (text or "").strip()

    for pattern in (
        rf"^{prefix}\s*{cmd}\s*$",
        rf"^{prefix}\s*{cmd}\s+(.+)$",
        rf"^{prefix}{cmd}$",
        rf"^{prefix}{cmd}(.+)$",
    ):
        match = re.match(pattern, raw, re.IGNORECASE)
        if match:
            if match.lastindex:
                return match.group(1).strip()
            return ""
    return None
