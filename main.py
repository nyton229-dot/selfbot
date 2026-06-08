import logging
import sys

import bot.fun_handlers  # noqa: F401 — trap (register early)
import bot.voice_handlers  # noqa: F401 — saved voice messages
import bot.feature_events  # noqa: F401 — register feature events
import bot.feature_handlers  # noqa: F401 — register nd/toggles
from bot import account_label, mirror_accounts, users
from bot.config import config
from bot.feature_tasks import cover_background_loop, feature_background_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _validate_tokens() -> None:
    for account, vk_user in zip(config.accounts, users, strict=True):
        try:
            await vk_user.api.users.get()
        except Exception as exc:
            logger.critical(
                "Токен VK не работает для аккаунта %s (%s). Нужен USER token (vk1.a...).",
                account_label(account),
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
        "VK user bot ready, accounts=%s, ssl_verify=%s, allow_self=%s",
        ", ".join(ids),
        config.ssl_verify,
        config.allow_self_messages,
    )
    logger.info("Меню функций: «нд» / «нд помощь»")


async def _start_extra_accounts() -> None:
    import asyncio

    if len(users) <= 1:
        return
    await asyncio.gather(*[vk_user.run_polling() for vk_user in users[1:]])


def _run() -> None:
    mirror_accounts()
    logger.info("Starting long poll for %s account(s)...", len(users))
    primary = users[0]

    if hasattr(primary, "startup_tasks"):
        primary.on_startup.append(_validate_tokens())
        primary.on_startup.append(_health_server())
        primary.on_startup.append(_startup())
        primary.startup_tasks.append(feature_background_loop())
        primary.startup_tasks.append(cover_background_loop())
        primary.startup_tasks.append(_start_extra_accounts())
        primary.run()
        return

    primary.loop_wrapper.on_startup.append(_validate_tokens())
    primary.loop_wrapper.on_startup.append(_health_server())
    primary.loop_wrapper.on_startup.append(_startup())
    primary.loop_wrapper.add_task(feature_background_loop())
    primary.loop_wrapper.add_task(cover_background_loop())
    primary.loop_wrapper.add_task(_start_extra_accounts())
    primary.run_forever()


if __name__ == "__main__":
    try:
        _run()
    except KeyboardInterrupt:
        sys.exit(0)
