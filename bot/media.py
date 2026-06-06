import asyncio
import base64
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from vkbottle.user import Message
from vkbottle_types.objects import AudioAudio, BaseImage, PhotosPhoto, PhotosPhotoSizes, VideoVideoFull

from bot.config import config
from bot.helpers import is_followup_query

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_VIDEO_MP4_BYTES = 20 * 1024 * 1024
MAX_VIDEO_FILE_BYTES = 50 * 1024 * 1024
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/*,audio/*,video/*,*/*;q=0.8",
    "Referer": "https://vk.com/",
}

VK_CDN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://vk.com/",
    "Origin": "https://vk.com",
}

FFMPEG_VK_HEADERS = (
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
    "Referer: https://vk.com/\r\n"
    "Origin: https://vk.com\r\n"
)


@dataclass
class MediaBundle:
    image_data_urls: list[str] = field(default_factory=list)
    audio_transcripts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    is_video_analysis: bool = False

    @property
    def has_content(self) -> bool:
        return bool(self.image_data_urls or self.audio_transcripts or self.notes)

    @property
    def has_images(self) -> bool:
        return bool(self.image_data_urls)


def _media_sources(message: Message) -> list[Any]:
    sources: list[Any] = [message]
    reply = getattr(message, "reply_message", None)
    if reply:
        sources.append(reply)
    for fwd in getattr(message, "fwd_messages", None) or []:
        sources.append(fwd)
    return sources


def _collect_sources(message: Message, query: str) -> list[Any]:
    if _source_has_media(message):
        return [message]

    if is_followup_query(query):
        return []

    sources: list[Any] = []
    reply = getattr(message, "reply_message", None)
    if reply and _source_has_media(reply):
        sources.append(reply)
    for fwd in getattr(message, "fwd_messages", None) or []:
        if _source_has_media(fwd):
            sources.append(fwd)
    return sources


def should_collect_media(message: Message, query: str) -> bool:
    return bool(_collect_sources(message, query))


def _source_has_media(source: Any) -> bool:
    return bool(
        source.get_photo_attachments()
        or source.get_video_attachments()
        or source.get_audio_message_attachments()
        or source.get_audio_attachments()
    )


def has_recognizable_media(message: Message) -> bool:
    return any(_source_has_media(source) for source in _media_sources(message))


def _largest_image_url(images: list[BaseImage] | None) -> str | None:
    if not images:
        return None
    best = max(images, key=lambda img: img.width * img.height)
    return best.url


def _largest_size_url(sizes: list[PhotosPhotoSizes] | None) -> str | None:
    if not sizes:
        return None
    with_url = [size for size in sizes if size.url]
    if not with_url:
        return None
    best = max(with_url, key=lambda size: size.width * size.height)
    return best.url


def _photo_url(photo: PhotosPhoto) -> str | None:
    for attr in (
        "photo_2560",
        "photo_256",
        "photo_1280",
        "photo_807",
        "photo_604",
        "photo_130",
        "photo_75",
    ):
        url = getattr(photo, attr, None)
        if url:
            return url

    url = _largest_image_url(photo.images)
    if url:
        return url

    return _largest_size_url(photo.sizes)


def _photo_api_id(photo: PhotosPhoto) -> str:
    photo_id = f"photo{photo.owner_id}_{photo.id}"
    if photo.access_key:
        photo_id += f"_{photo.access_key}"
    return photo_id


async def _resolve_photo_url(photo: PhotosPhoto) -> str | None:
    url = _photo_url(photo)
    if url:
        return url

    from bot import user

    try:
        items = await user.api.photos.get_by_id(
            photos=[_photo_api_id(photo)],
            photo_sizes=True,
        )
    except Exception as exc:
        logger.warning("photos.getById failed for %s: %s", _photo_api_id(photo), exc)
        return None

    if not items:
        return None

    resolved = _photo_url(items[0])
    if resolved:
        logger.info("Resolved photo URL via API: %s", _photo_api_id(photo))
    return resolved


def _video_api_id(video: VideoVideoFull) -> str:
    video_id = f"{video.owner_id}_{video.id}"
    if video.access_key:
        video_id += f"_{video.access_key}"
    return video_id


async def _resolve_video(video: VideoVideoFull) -> VideoVideoFull:
    from bot import user

    try:
        result = await user.api.video.get(videos=[_video_api_id(video)])
    except Exception as exc:
        logger.warning("video.get failed for %s: %s", _video_api_id(video), exc)
        return video

    if not result.items:
        return video

    logger.info("Resolved video via API: %s", _video_api_id(video))
    return result.items[0]


def _video_preview_urls(video: VideoVideoFull) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for images in (video.first_frame, video.image):
        if not images:
            continue
        for img in images:
            ranked.append((img.width * img.height, img.url))

    ranked.sort(key=lambda item: item[0], reverse=True)

    seen: set[str] = set()
    urls: list[str] = []
    for _, url in ranked:
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _frame_timestamps(duration: float, max_frames: int) -> list[float]:
    safe_duration = max(duration, 1.0)
    max_frames = max(max_frames, 1)
    step = safe_duration / max_frames
    step = max(step, 0.5)

    timestamps: list[float] = []
    pos = min(0.3, step / 2)
    while pos < safe_duration and len(timestamps) < max_frames:
        timestamps.append(round(pos, 2))
        pos += step

    return timestamps or [0.3]


def _ffmpeg_stderr_tail(stderr: str, lines: int = 6) -> str:
    parts = [line for line in stderr.strip().splitlines() if line.strip()]
    return "\n".join(parts[-lines:])[:500]


async def _run_ffmpeg(args: list[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    return proc.returncode or 0, stderr.decode(errors="replace")


def _ffmpeg_input_args() -> list[str]:
    return [
        "-protocol_whitelist",
        "file,http,https,tcp,tls,crypto",
        "-headers",
        FFMPEG_VK_HEADERS,
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "5",
    ]


async def _probe_duration(video_path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None

    proc = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None

    try:
        return float(stdout.decode().strip())
    except ValueError:
        return None


async def _download_video_via_http(
    client: httpx.AsyncClient, url: str, output_path: Path
) -> bool:
    try:
        async with client.stream(
            "GET", url, headers=VK_CDN_HEADERS, follow_redirects=True
        ) as response:
            response.raise_for_status()
            size = 0
            with output_path.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_VIDEO_FILE_BYTES:
                        logger.warning("HTTP video too large: %s", url[:80])
                        return False
                    handle.write(chunk)
    except httpx.HTTPError as exc:
        logger.warning("HTTP video download failed %s: %s", url[:80], exc)
        return False

    return output_path.exists() and output_path.stat().st_size > 0


async def _download_video_file(
    urls: list[str],
    output_path: Path,
    client: httpx.AsyncClient | None = None,
) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    encode_args = (
        ["-c", "copy"],
        ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-movflags", "+faststart"],
        ["-c:v", "libx264", "-preset", "ultrafast", "-an"],
    )

    for url in urls:
        if ffmpeg:
            for extra in encode_args:
                if output_path.exists():
                    output_path.unlink(missing_ok=True)

                code, stderr = await _run_ffmpeg(
                    [
                        ffmpeg,
                        "-y",
                        *_ffmpeg_input_args(),
                        "-i",
                        url,
                        *extra,
                        str(output_path),
                    ]
                )
                if code == 0 and output_path.exists() and output_path.stat().st_size > 0:
                    logger.info(
                        "Video downloaded via ffmpeg (%d bytes)",
                        output_path.stat().st_size,
                    )
                    return True
                logger.warning(
                    "ffmpeg video download failed: %s",
                    _ffmpeg_stderr_tail(stderr),
                )

        if client:
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            if await _download_video_via_http(client, url, output_path):
                logger.info(
                    "Video downloaded via HTTP (%d bytes)",
                    output_path.stat().st_size,
                )
                return True

    return False


async def _probe_duration_from_url(url: str) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None

    proc = await asyncio.create_subprocess_exec(
        ffprobe,
        "-v",
        "error",
        "-protocol_whitelist",
        "file,http,https,tcp,tls,crypto",
        "-headers",
        FFMPEG_VK_HEADERS,
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        "-i",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None

    try:
        return float(stdout.decode().strip())
    except ValueError:
        return None


async def _extract_audio_from_url(url: str, output_path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False

    code, stderr = await _run_ffmpeg(
        [
            ffmpeg,
            "-y",
            *_ffmpeg_input_args(),
            "-i",
            url,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "4",
            str(output_path),
        ]
    )
    if code != 0:
        logger.warning("ffmpeg audio extract failed: %s", _ffmpeg_stderr_tail(stderr))
        return False

    return output_path.exists() and output_path.stat().st_size > 0


async def _extract_audio_track(video_path: Path, audio_path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False

    code, _ = await _run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "aac",
            "-b:a",
            "64k",
            str(audio_path),
        ]
    )
    return code == 0 and audio_path.exists() and audio_path.stat().st_size > 0


async def _extract_video_frames(
    video_path: Path, duration: float, max_frames: int
) -> list[tuple[bytes, str]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []

    timestamps = _frame_timestamps(duration, max_frames)
    frames: list[tuple[bytes, str]] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for index, timestamp in enumerate(timestamps):
            output_path = Path(tmp_dir) / f"frame_{index:03d}.jpg"
            code, _ = await _run_ffmpeg(
                [
                    ffmpeg,
                    "-y",
                    "-ss",
                    str(timestamp),
                    "-i",
                    str(video_path),
                    "-vframes",
                    "1",
                    "-q:v",
                    "4",
                    str(output_path),
                ]
            )
            if code != 0 or not output_path.exists():
                continue
            data = output_path.read_bytes()
            if data:
                frames.append((data, "image/jpeg"))

    return frames


async def _transcribe_video_audio(
    bundle: MediaBundle,
    client: httpx.AsyncClient,
    audio_path: Path,
) -> None:
    audio_data = audio_path.read_bytes()
    if not audio_data or len(audio_data) > MAX_AUDIO_BYTES:
        return

    transcript = await _transcribe_audio(client, audio_data, audio_path.name)
    if transcript:
        bundle.audio_transcripts.append(f"Звук из видео: {transcript}")


async def _analyze_full_video(
    bundle: MediaBundle,
    client: httpx.AsyncClient,
    video: VideoVideoFull,
    title: str,
    duration: int,
) -> bool:
    source_urls = _video_source_urls(video)
    if not source_urls:
        return False

    total_duration = float(duration or 0) or 30.0
    frames: list[tuple[bytes, str]] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = Path(tmp_dir) / "video.mp4"
        if await _download_video_file(source_urls, video_path, client):
            probed = await _probe_duration(video_path)
            if probed:
                total_duration = probed

            audio_path = Path(tmp_dir) / "audio.m4a"
            if await _extract_audio_track(video_path, audio_path):
                await _transcribe_video_audio(bundle, client, audio_path)

            frames = await _extract_video_frames(
                video_path, total_duration, config.ai_video_max_frames
            )
        else:
            logger.info("File download failed, trying stream extraction from URL")
            for url in source_urls:
                probed = await _probe_duration_from_url(url)
                if probed:
                    total_duration = probed
                    break

            for url in source_urls:
                audio_path = Path(tmp_dir) / "audio.mp3"
                if await _extract_audio_from_url(url, audio_path):
                    await _transcribe_video_audio(bundle, client, audio_path)
                    break

            for url in source_urls:
                frames = await _extract_frames_from_url(
                    url, total_duration, config.ai_video_max_frames
                )
                if frames:
                    break

    if not frames and not bundle.audio_transcripts:
        return False

    for data, mime in frames:
        bundle.image_data_urls.append(_to_data_url(data, mime))

    bundle.is_video_analysis = True
    parts = [f"Видео «{title}»"]
    if frames:
        parts.append(f"{len(frames)} кадров по ролику")
    if bundle.audio_transcripts:
        parts.append("распознан звук")
    if total_duration:
        parts.append(f"{int(total_duration)} с")
    bundle.notes.append(": ".join(parts[:1]) + " — " + ", ".join(parts[1:]) + ".")

    logger.info(
        "Full video analysis: frames=%d audio=%s duration=%.1fs",
        len(frames),
        bool(bundle.audio_transcripts),
        total_duration,
    )
    return True


def _video_source_urls(video: VideoVideoFull) -> list[str]:
    files = video.files
    if not files:
        return []

    urls: list[str] = []
    for attr in (
        "mp4_144",
        "mp4_240",
        "mp4_360",
        "mp4_480",
        "mp4_720",
        "mp4_1080",
        "flv_320",
    ):
        url = getattr(files, attr, None)
        if url:
            urls.append(url)

    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _video_mp4_urls(video: VideoVideoFull) -> list[str]:
    return _video_source_urls(video)


async def _extract_frame_from_url(
    url: str, timestamp: float = 0.5
) -> tuple[bytes, str] | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "frame.jpg"
        code, stderr = await _run_ffmpeg(
            [
                ffmpeg,
                "-y",
                *_ffmpeg_input_args(),
                "-ss",
                str(timestamp),
                "-i",
                url,
                "-vframes",
                "1",
                "-q:v",
                "4",
                str(output_path),
            ]
        )
        if code != 0 or not output_path.exists():
            logger.warning(
                "ffmpeg frame at %.1fs failed: %s",
                timestamp,
                _ffmpeg_stderr_tail(stderr),
            )
            return None

        data = output_path.read_bytes()
        if not data:
            return None
        return data, "image/jpeg"


async def _extract_frames_from_url(
    url: str, duration: float, max_frames: int
) -> list[tuple[bytes, str]]:
    frames: list[tuple[bytes, str]] = []
    for timestamp in _frame_timestamps(duration, max_frames):
        frame = await _extract_frame_from_url(url, timestamp)
        if frame:
            frames.append(frame)
    return frames


async def _extract_video_frame(mp4_data: bytes) -> tuple[bytes, str] | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("ffmpeg not found, cannot extract video frame")
        return None

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        input_path = tmp / "video.mp4"
        output_path = tmp / "frame.jpg"
        input_path.write_bytes(mp4_data)

        proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(output_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0 or not output_path.exists():
            logger.warning("ffmpeg frame extraction failed (code=%s)", proc.returncode)
            return None

        data = output_path.read_bytes()
        if not data:
            return None
        return data, "image/jpeg"


def _guess_image_mime(data: bytes, content_type: str | None) -> str:
    if content_type and content_type.startswith("image/"):
        return content_type.split(";")[0].strip()

    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


async def _download_bytes(
    client: httpx.AsyncClient,
    url: str,
    max_bytes: int,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, str] | None:
    content_type: str | None = None
    try:
        async with client.stream(
            "GET", url, headers=headers or DOWNLOAD_HEADERS, follow_redirects=True
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    logger.warning("Download too large: %s", url[:80])
                    return None
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        logger.warning("Download failed %s: %s", url[:80], exc)
        return None

    data = b"".join(chunks)
    if not data:
        logger.warning("Download empty: %s", url[:80])
        return None

    mime = _guess_image_mime(data, content_type)
    return data, mime


def _to_data_url(data: bytes, content_type: str) -> str:
    mime = content_type.split(";")[0].strip() or "application/octet-stream"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


async def _transcribe_audio(client: httpx.AsyncClient, data: bytes, filename: str) -> str | None:
    url = f"{config.ai_base_url.rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {config.ai_api_key}"}
    files = {"file": (filename, data)}
    data_form = {"model": config.ai_whisper_model, "language": "ru"}

    try:
        response = await client.post(url, headers=headers, files=files, data=data_form)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Whisper HTTP error %s: %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return None
    except httpx.HTTPError as exc:
        logger.error("Whisper request failed: %s", exc)
        return None
    except (KeyError, TypeError) as exc:
        logger.error("Whisper response parse error: %s", exc)
        return None

    text = str(payload.get("text", "")).strip()
    return text or None


async def _add_photo(bundle: MediaBundle, client: httpx.AsyncClient, photo: PhotosPhoto) -> None:
    url = await _resolve_photo_url(photo)
    if not url:
        bundle.notes.append("Фото: не удалось получить ссылку.")
        return

    downloaded = await _download_bytes(client, url, MAX_IMAGE_BYTES)
    if not downloaded:
        bundle.notes.append("Фото: не удалось скачать.")
        return

    data, mime = downloaded
    bundle.image_data_urls.append(_to_data_url(data, mime))
    logger.info("Photo ready for vision (%d bytes)", len(data))


async def _try_video_preview(
    bundle: MediaBundle,
    client: httpx.AsyncClient,
    urls: list[str],
    note: str,
) -> bool:
    header_sets = (DOWNLOAD_HEADERS, VK_CDN_HEADERS)
    for url in urls:
        for headers in header_sets:
            downloaded = await _download_bytes(client, url, MAX_IMAGE_BYTES, headers)
            if not downloaded:
                continue
            data, mime = downloaded
            bundle.image_data_urls.append(_to_data_url(data, mime))
            bundle.notes.append(note)
            logger.info("Video preview ready for vision (%d bytes)", len(data))
            return True
    return False


async def _add_video(bundle: MediaBundle, client: httpx.AsyncClient, video: VideoVideoFull) -> None:
    title = (video.title or "без названия").strip()
    duration = video.duration or 0
    resolved = await _resolve_video(video)

    if await _analyze_full_video(bundle, client, resolved, title, duration):
        return

    note = f"Видео «{title}» ({duration} с): один кадр (mp4 недоступен)."

    if await _try_video_preview(bundle, client, _video_preview_urls(resolved), note):
        return

    for mp4_url in _video_source_urls(resolved):
        frame = await _extract_frame_from_url(mp4_url)
        if frame:
            data, mime = frame
            bundle.image_data_urls.append(_to_data_url(data, mime))
            bundle.notes.append(note + " Кадр извлечён из mp4.")
            logger.info("Video frame extracted from mp4 URL (%d bytes)", len(data))
            return

        downloaded = await _download_bytes(
            client, mp4_url, MAX_VIDEO_MP4_BYTES, VK_CDN_HEADERS
        )
        if not downloaded:
            continue
        frame = await _extract_video_frame(downloaded[0])
        if frame:
            data, mime = frame
            bundle.image_data_urls.append(_to_data_url(data, mime))
            bundle.notes.append(note + " Кадр извлечён из mp4.")
            logger.info("Video frame extracted from mp4 (%d bytes)", len(data))
            return

    bundle.notes.append(
        f"Видео «{title}» ({duration} с): не удалось получить кадр для анализа."
    )


async def _collect_from_source(bundle: MediaBundle, client: httpx.AsyncClient, source: Any) -> None:
    for photo in source.get_photo_attachments() or []:
        await _add_photo(bundle, client, photo)

    for video in source.get_video_attachments() or []:
        await _add_video(bundle, client, video)

    for voice in source.get_audio_message_attachments() or []:
        url = voice.link_mp3 or voice.link_ogg
        if not url:
            bundle.notes.append("Голосовое сообщение: ссылка недоступна.")
            continue
        downloaded = await _download_bytes(client, url, MAX_AUDIO_BYTES)
        if not downloaded:
            bundle.notes.append("Голосовое сообщение: не удалось скачать.")
            continue
        data, _ = downloaded
        ext = "mp3" if voice.link_mp3 else "ogg"
        transcript = await _transcribe_audio(client, data, f"voice.{ext}")
        if transcript:
            bundle.audio_transcripts.append(transcript)
        else:
            bundle.notes.append("Голосовое сообщение: не удалось распознать речь.")

    for audio in source.get_audio_attachments() or []:
        await _handle_music_audio(client, bundle, audio)


async def collect_media(message: Message, query: str = "") -> MediaBundle:
    bundle = MediaBundle()

    async with httpx.AsyncClient(timeout=config.ai_timeout, verify=config.ssl_verify) as client:
        for source in _collect_sources(message, query):
            await _collect_from_source(bundle, client, source)

    logger.info(
        "Media collected: images=%d transcripts=%d notes=%d",
        len(bundle.image_data_urls),
        len(bundle.audio_transcripts),
        len(bundle.notes),
    )
    return bundle


async def _handle_music_audio(
    client: httpx.AsyncClient, bundle: MediaBundle, audio: AudioAudio
) -> None:
    label = f"{audio.artist} — {audio.title}".strip(" —")
    if not audio.url:
        bundle.notes.append(f"Аудио «{label}»: файл недоступен (только метаданные).")
        return

    downloaded = await _download_bytes(client, audio.url, MAX_AUDIO_BYTES)
    if not downloaded:
        bundle.notes.append(f"Аудио «{label}»: не удалось скачать.")
        return

    data, _ = downloaded
    transcript = await _transcribe_audio(client, data, "audio.mp3")
    if transcript:
        bundle.audio_transcripts.append(f"«{label}»: {transcript}")
    else:
        bundle.notes.append(f"Аудио «{label}»: не удалось распознать.")
