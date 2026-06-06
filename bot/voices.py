import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from vkbottle_types.objects import MessagesAudioMessage

from bot.features import get_state

logger = logging.getLogger(__name__)

VOICES_FILE = Path(__file__).resolve().parent.parent / "data" / "voices.json"


@dataclass
class SavedVoice:
    name: str
    attachment: str
    owner_id: int
    doc_id: int
    access_key: str | None = None


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def voice_to_attachment(voice: MessagesAudioMessage) -> str:
    attachment = f"doc{voice.owner_id}_{voice.id}"
    if voice.access_key:
        attachment += f"_{voice.access_key}"
    return attachment


def extract_voice_attachment(source) -> str | None:
    getter = getattr(source, "get_audio_message_attachments", None)
    if not getter:
        return None
    voices = getter() or []
    if not voices:
        return None
    return voice_to_attachment(voices[0])


def _load_raw() -> dict:
    if not VOICES_FILE.is_file():
        return {}
    try:
        return json.loads(VOICES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load voices: %s", exc)
        return {}


def _save_raw(data: dict) -> None:
    VOICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    VOICES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_voices() -> list[str]:
    return sorted(_load_raw().keys())


def get_voice(name: str) -> SavedVoice | None:
    raw = _load_raw()
    entry = raw.get(_normalize_name(name))
    if not entry:
        return None
    return SavedVoice(**entry)


def save_voice(name: str, voice: MessagesAudioMessage) -> SavedVoice:
    key = _normalize_name(name)
    if not key:
        raise ValueError("empty name")

    saved = SavedVoice(
        name=name.strip(),
        attachment=voice_to_attachment(voice),
        owner_id=voice.owner_id,
        doc_id=voice.id,
        access_key=voice.access_key,
    )
    data = _load_raw()
    data[key] = asdict(saved)
    _save_raw(data)
    logger.info("Saved voice %r -> %s", saved.name, saved.attachment)
    return saved


def delete_voice(name: str) -> bool:
    key = _normalize_name(name)
    data = _load_raw()
    if key not in data:
        return False
    del data[key]
    _save_raw(data)
    logger.info("Deleted voice %r", name)
    return True


def parse_voice_command(text: str) -> tuple[str, str] | None:
    """('save' | 'delete' | 'send', name) или None."""
    state = get_state()
    prefix = re.escape(state.command_prefix.strip())
    raw = (text or "").strip()

    patterns = (
        ("save", rf"^{prefix}\s*\+гс\s+(.+)$"),
        ("delete", rf"^{prefix}\s*-гс\s+(.+)$"),
        ("send", rf"^{prefix}\s*гс\s+(.+)$"),
    )
    for action, pattern in patterns:
        match = re.match(pattern, raw, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name:
                return action, name
    return None
