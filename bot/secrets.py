import os
from pathlib import Path

AI_KEY_FILES = ("ai_api_key.txt", "bothub_api_key.txt")


def _data_dirs() -> list[Path]:
    dirs: list[Path] = []
    data_dir = os.environ.get("DATA_DIR", "").strip()
    if data_dir:
        dirs.append(Path(data_dir))
    dirs.append(Path(__file__).resolve().parent.parent / "data")
    return dirs


def get_ai_api_key() -> str:
    for name in ("AI_API_KEY", "BOTHUB_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value

    for directory in _data_dirs():
        for filename in AI_KEY_FILES:
            path = directory / filename
            if path.is_file():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value
    return ""


def save_ai_api_key(key: str) -> Path:
    value = key.strip()
    if not value:
        raise ValueError("empty key")

    for directory in _data_dirs():
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "ai_api_key.txt"
        path.write_text(value, encoding="utf-8")
        return path

    raise RuntimeError("no data directory")


def is_ai_enabled(base_url: str) -> bool:
    return bool(get_ai_api_key() and base_url.strip())
