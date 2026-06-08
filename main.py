import logging
import sys

import bot.fun_handlers  # noqa: F401 — trap (register early)
import bot.voice_handlers  # noqa: F401 — saved voice messages
import bot.feature_events  # noqa: F401 — register feature events
import bot.feature_handlers  # noqa: F401 — register nd/toggles
from bot import account_label, apis, user
from bot.api_context import account_for_api
from bot.config import config
from bot.feature_tasks import cover_background_loop, feature_background_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _validate_tokens() -> None:
    for api in apis:
        account = account_for_api(api)
        label = account_label(account) if account else "?"
        try:
            me = (await api.users.get())[0]
            logger.info("VK token OK: account %s (%s %s)", label, me.first_name, me.last_name)
        except Exception as exc:
            logger.critical(
                "Токен VK не работает для аккаунта %s (%s). Нужен USER token (vk1.a...).",
                label,
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
    ids = [account_label(account) for account in config.accounts]
    logger.info(
        "VK user bot ready, accounts=%s (%d), ssl_verify=%s, allow_self=%s",
        ", ".join(ids),
        len(config.accounts),
        config.ssl_verify,
        config.allow_self_messages,
    )
    if len(config.accounts) == 1:
        logger.warning(
            "Загружен 1 аккаунт. Для второго добавь VK_TOKEN_2 и VK_USER_ID_2 в переменные окружения."
        )
    logger.info("Меню функций: «нд» / «нд помощь»")


async def _run_all_polls() -> None:
    import asyncio

    from vkbottle.polling import UserPolling

    async def _poll_api(api) -> None:
        account = account_for_api(api)
        label = account_label(account) if account else "?"
        polling = UserPolling().construct(api, user.error_handler)
        logger.info("Long poll started for account %s", label)
        await user.run_polling(custom_polling=polling)

    await asyncio.gather(*[_poll_api(api) for api in apis])


def _run() -> None:
    logger.info("Starting long poll for %s account(s)...", len(apis))

    if hasattr(user, "startup_tasks"):
        user.on_startup.append(_validate_tokens())
        user.on_startup.append(_health_server())
        user.on_startup.append(_startup())
        user.startup_tasks.append(feature_background_loop())
        user.startup_tasks.append(cover_background_loop())
        user.startup_tasks.append(_run_all_polls())
        user.run()
        return

    user.loop_wrapper.on_startup.append(_validate_tokens())
    user.loop_wrapper.on_startup.append(_health_server())
    user.loop_wrapper.on_startup.append(_startup())
    user.loop_wrapper.add_task(feature_background_loop())
    user.loop_wrapper.add_task(cover_background_loop())
    user.loop_wrapper.add_task(_run_all_polls())
    user.loop_wrapper.run()


if __name__ == "__main__":
    try:
        _run()
    except KeyboardInterrupt:
        sys.exit(0)
