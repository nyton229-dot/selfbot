import logging

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


if __name__ == "__main__":
    user.loop_wrapper.add_task(_startup())
    user.loop_wrapper.add_task(feature_background_loop())
    user.loop_wrapper.add_task(cover_background_loop())
    logger.info("Starting long poll...")
    user.run_forever()
