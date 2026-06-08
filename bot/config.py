import os
from dataclasses import dataclass
from pathlib import Path

ARTEM_SYSTEM_PROMPT_FILE = Path(__file__).parent / "prompts" / "artem_system.txt"


def _load_default_system_prompt() -> str:
    if ARTEM_SYSTEM_PROMPT_FILE.is_file():
        return ARTEM_SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
    return ""


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    root = Path(__file__).resolve().parent.parent
    data_dir = os.environ.get("DATA_DIR", "").strip()
    candidates = [root / ".env"]
    if data_dir:
        candidates.append(Path(data_dir) / ".env")

    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)


@dataclass(frozen=True)
class VkAccount:
    token: str
    user_id: int


@dataclass(frozen=True)
class Config:
    accounts: tuple[VkAccount, ...]
    port: int
    ai_api_key: str
    ai_base_url: str
    ai_model: str
    ai_prefix: str
    ai_system_prompt: str
    ai_media_prompt: str
    ai_whisper_model: str
    ai_video_max_frames: int
    ai_timeout: float
    ssl_verify: bool
    allow_self_messages: bool

    @property
    def vk_token(self) -> str:
        return self.accounts[0].token

    @property
    def vk_user_id(self) -> int:
        return self.accounts[0].user_id

    @property
    def ai_enabled(self) -> bool:
        from bot.secrets import get_ai_api_key

        return bool(get_ai_api_key() and self.ai_base_url)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _read_token(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _read_user_id(name: str) -> int:
    raw = os.environ.get(name, "0").strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _load_accounts() -> tuple[VkAccount, ...]:
    primary_token = _read_token("VK_TOKEN", "BOT_TOKEN", "VK_BOT_TOKEN")
    if not primary_token:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        raise RuntimeError(
            "VK_TOKEN не задан. Локально — в .env, на Bothost — в переменных окружения:\n"
            f"  {env_path}\n"
            "  VK_TOKEN=vk1.a.... (user access token из oauth.vk.com)"
        )

    accounts = [
        VkAccount(token=primary_token, user_id=_read_user_id("VK_USER_ID")),
    ]

    second_token = os.environ.get("VK_TOKEN_2", "").strip()
    if second_token:
        accounts.append(
            VkAccount(token=second_token, user_id=_read_user_id("VK_USER_ID_2")),
        )

    return tuple(accounts)


def load_config() -> Config:
    _load_dotenv()

    from bot.secrets import get_ai_api_key

    return Config(
        accounts=_load_accounts(),
        port=int(os.environ.get("PORT", "8080")),
        ai_api_key=get_ai_api_key(),
        ai_base_url=os.environ.get(
            "AI_BASE_URL", "https://bothub.chat/api/v2/openai/v1"
        ).strip(),
        ai_model=os.environ.get("AI_MODEL", "gpt-4o").strip(),
        ai_prefix=os.environ.get("AI_PREFIX", "Артем").strip(),
        ai_system_prompt=(
            os.environ.get("AI_SYSTEM_PROMPT", "").strip()
            or _load_default_system_prompt()
        ),
        ai_media_prompt=os.environ.get(
            "AI_MEDIA_PROMPT",
            "Разбери вложения и ответь в своём токсичном стиле.",
        ).strip(),
        ai_whisper_model=os.environ.get("AI_WHISPER_MODEL", "whisper-1").strip(),
        ai_video_max_frames=int(os.environ.get("AI_VIDEO_MAX_FRAMES", "16")),
        ai_timeout=float(os.environ.get("AI_TIMEOUT", "180")),
        ssl_verify=_env_bool("SSL_VERIFY", _env_bool("VK_SSL_VERIFY", True)),
        allow_self_messages=_env_bool("ALLOW_SELF_MESSAGES", True),
    )


config = load_config()
