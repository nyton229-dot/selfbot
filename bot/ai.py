import logging

import httpx

from bot.config import config
from bot.media import MediaBundle

logger = logging.getLogger(__name__)

VK_MESSAGE_LIMIT = 4096


def _build_user_text(user_text: str, media: MediaBundle | None) -> str:
    parts: list[str] = []

    if media:
        if media.audio_transcripts:
            parts.append(
                "Транскрипция аудио:\n" + "\n".join(media.audio_transcripts)
            )
        if media.notes:
            parts.append("\n".join(media.notes))

    query = user_text.strip()
    if query:
        parts.append(query)
    elif media and media.has_content:
        parts.append(config.ai_media_prompt)

    return "\n\n".join(parts).strip()


def _build_user_content(user_text: str, media: MediaBundle | None) -> str | list[dict]:
    text = _build_user_text(user_text, media)
    if not media or not media.image_data_urls:
        return text

    content: list[dict] = [{"type": "text", "text": text}]
    detail = "low" if len(media.image_data_urls) > 4 else "auto"
    for data_url in media.image_data_urls:
        content.append(
            {"type": "image_url", "image_url": {"url": data_url, "detail": detail}}
        )
    return content


async def generate_reply(
    user_text: str, media: MediaBundle | None = None
) -> str | None:
    if not config.ai_enabled:
        return None

    prompt = _build_user_text(user_text, media)
    if not prompt:
        return None

    messages: list[dict] = [
        {"role": "user", "content": _build_user_content(user_text, media)}
    ]
    system_prompt = config.ai_system_prompt
    if media and media.has_images:
        if media.is_video_analysis:
            system_prompt = (
                f"{system_prompt}\n\n"
                "К сообщению приложены кадры и/или транскрипция звука из видео. "
                "Используй их в ответе. Если просят текст песни — возьми из транскрипции."
            ).strip()
        else:
            system_prompt = (
                f"{system_prompt}\n\n"
                "К сообщению приложены изображения — ты их видишь, используй в ответе."
            ).strip()
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})

    url = f"{config.ai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.ai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.ai_model,
        "messages": messages,
        "temperature": 0.7,
    }

    try:
        async with httpx.AsyncClient(
            timeout=config.ai_timeout, verify=config.ssl_verify
        ) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("AI HTTP error %s: %s", exc.response.status_code, exc.response.text[:300])
        return None
    except httpx.HTTPError as exc:
        logger.error("AI request failed: %s", exc)
        return None
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("AI response parse error: %s", exc)
        return None

    content = data["choices"][0]["message"]["content"]
    text = str(content).strip()
    if not text:
        return None

    if len(text) > VK_MESSAGE_LIMIT:
        return text[: VK_MESSAGE_LIMIT - 3] + "..."

    return text
