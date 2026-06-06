import asyncio
import time

_lock = asyncio.Lock()
_last_call = 0.0
MIN_INTERVAL = 0.35


async def throttle() -> None:
    """Пауза между запросами к VK API, чтобы не ловить error 6."""
    global _last_call
    async with _lock:
        now = time.monotonic()
        wait = MIN_INTERVAL - (now - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()


async def cooldown(seconds: float = 1.5) -> None:
    """Пауза после тяжёлой пачки запросов перед отправкой ответа."""
    await asyncio.sleep(seconds)
