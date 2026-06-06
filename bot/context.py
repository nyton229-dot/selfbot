from bot.helpers import is_followup_query

_last_exchange: dict[int, dict[str, str]] = {}


def save_exchange(peer_id: int, query: str, reply: str) -> None:
    _last_exchange[peer_id] = {"query": query, "reply": reply}


def get_context_prefix(peer_id: int, query: str) -> str:
    if not is_followup_query(query):
        return ""

    prev = _last_exchange.get(peer_id)
    if not prev:
        return ""

    return (
        f"Предыдущий вопрос пользователя: {prev['query']}\n"
        f"Твой предыдущий ответ: {prev['reply']}\n\n"
    )
