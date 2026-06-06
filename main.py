import logging
import sys

import bot.fun_handlers  # noqa: F401 — trap (register early)
import bot.voice_handlers  # noqa: F401 — saved voice messages
import bot.feature_events  # noqa: F401 — register feature events
import bot.feature_handlers  # noqa: F401 — register nd/toggles
import bot.handlers  # noqa: F401 — register handlers
from bot import get_self_id, user
from bot.config import config
from bot.feature_tasks import cover_background_loop, feature_background_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _validate_token() -> None:
    try:
        await user.api.users.get()
    except Exception as exc:
        logger.critical(
            "Токен VK не работает (%s). На Bothost нужен USER token (vk1.a...), "
            "не токен группы/сообщества. Проверь VK_TOKEN в переменных окружения.",
            exc,
        )
        raise SystemExit(1) from exc


async def _health_server() -> None:
    """Bothost проверяет PORT — без HTTP-ответа контейнер могут остановить."""
    from aiohttp import web

    async def ok(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.port)
    await site.start()
    logger.info("Health server on port %s", config.port)


async def _startup() -> None:
    self_id = await get_self_id()
    logger.info(
        "VK user bot ready, user_id=%s, ai=%s, ssl_verify=%s, allow_self=%s",
        self_id,
        config.ai_enabled,
        config.ssl_verify,
        config.allow_self_messages,
    )
    logger.info("Команда для ответа: «%s твой вопрос» (только ты + выданный /+дов)", config.ai_prefix)
    logger.info("Меню функций: «нд» / «нд помощь»")


def _run() -> None:
    logger.info("Starting long poll...")

    if hasattr(user, "startup_tasks"):
        user.on_startup.append(_validate_token())
        user.on_startup.append(_health_server())
        user.on_startup.append(_startup())
        user.startup_tasks.append(feature_background_loop())
        user.startup_tasks.append(cover_background_loop())
        user.run()
        return

    user.loop_wrapper.on_startup.append(_validate_token())
    user.loop_wrapper.on_startup.append(_health_server())
    user.loop_wrapper.on_startup.append(_startup())
    user.loop_wrapper.add_task(feature_background_loop())
    user.loop_wrapper.add_task(cover_background_loop())
    user.run_forever()


if __name__ == "__main__":
    try:
        _run()
    except KeyboardInterrupt:
        sys.exit(0)
