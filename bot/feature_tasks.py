import asyncio
import logging

from vkbottle_types.objects import UsersFields

from bot import user
from bot.cover_updater import msk_now, sleep_until_next_msk_minute, update_profile_cover
from bot.feature_events import _self_removed_friends
from bot.features import get_friend_ids, get_state, set_friend_ids

logger = logging.getLogger(__name__)

_online_unavailable = False
_offline_unavailable = False


async def run_feature_maintenance() -> None:
    state = get_state()

    if state.eternal_online:
        await _set_online()
    elif state.eternal_offline:
        await _set_offline()

    if state.auto_add_friends:
        await _process_friend_requests()

    if state.delete_dogs:
        await _delete_dogs()

    if state.auto_unfollow:
        await _process_auto_unfollow()


async def _set_online() -> None:
    global _online_unavailable
    if _online_unavailable:
        return
    try:
        await user.api.account.set_online()
    except Exception as exc:
        code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
        if code == 3:
            _online_unavailable = True
            logger.warning(
                "account.setOnline недоступен для этого токена — вечный онлайн отключён"
            )
            return
        logger.exception("setOnline failed")


async def _set_offline() -> None:
    global _offline_unavailable
    if _offline_unavailable:
        return
    try:
        await user.api.account.set_offline()
    except Exception as exc:
        code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
        if code == 3:
            _offline_unavailable = True
            logger.warning(
                "account.setOffline недоступен для этого токена — вечный оффлайн отключён"
            )
            return
        logger.exception("setOffline failed")


async def _process_friend_requests() -> None:
    try:
        requests = await user.api.friends.get_requests()
    except Exception:
        logger.exception("friends.getRequests failed")
        return

    for user_id in requests.items or []:
        try:
            await user.api.friends.add(user_id=user_id)
            logger.info("Auto-added friend %s", user_id)
        except Exception:
            logger.warning("friends.add failed for %s", user_id)


async def _delete_dogs() -> None:
    try:
        friends = await user.api.friends.get(fields=[UsersFields.DEACTIVATED])
    except Exception:
        logger.exception("friends.get failed")
        return

    for profile in friends.items or []:
        deactivated = getattr(profile, "deactivated", None)
        if not deactivated:
            continue
        try:
            await user.api.friends.delete(user_id=profile.id)
            logger.info("Removed dog account %s (%s)", profile.id, deactivated)
        except Exception:
            logger.warning("friends.delete failed for %s", profile.id)


async def _process_auto_unfollow() -> None:
    try:
        friends = await user.api.friends.get()
    except Exception:
        logger.exception("friends.get failed")
        return

    current = set(friends.items or [])
    previous = get_friend_ids()

    if not previous:
        set_friend_ids(sorted(current))
        return

    removed = previous - current
    for user_id in removed:
        if user_id in _self_removed_friends:
            _self_removed_friends.discard(user_id)
            continue
        try:
            await user.api.friends.delete(user_id=user_id)
            logger.info("Auto-unfollow %s", user_id)
        except Exception:
            logger.warning("Auto-unfollow failed for %s", user_id)

    set_friend_ids(sorted(current))


async def cover_background_loop() -> None:
    """Обновляет обложку по МСК в начале каждой минуты."""
    last_posted_minute = ""

    while True:
        if not get_state().dynamic_cover:
            last_posted_minute = ""
            await sleep_until_next_msk_minute()
            continue

        current_minute = msk_now().strftime("%H:%M")
        if current_minute != last_posted_minute:
            try:
                await update_profile_cover()
                last_posted_minute = current_minute
            except Exception as exc:
                code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
                if code in {15, 200, 203}:
                    logger.warning(
                        "Обложка профиля недоступна для этого токена (код %s) — выключи «нд выкл обложка»",
                        code,
                    )
                else:
                    logger.exception("Profile cover update failed")

        await sleep_until_next_msk_minute()


async def feature_background_loop() -> None:
    while True:
        try:
            await run_feature_maintenance()
        except Exception:
            logger.exception("Feature maintenance error")
        await asyncio.sleep(30)
