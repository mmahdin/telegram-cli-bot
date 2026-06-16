from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


ProxyConfig = Tuple[str, str, int]


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str

    # Telethon will use exactly this file name: session.session
    session_name: str = "session"

    # Telegram channel/chat that contains the source audio messages.
    source_chat: str = "ahangd00ni"

    # Command format: آهنگ <telegram_message_id> <start> <end>
    audio_command: str = "آهنگ"

    download_dir: Path = Path("downloaded_audios")
    proxy: Optional[ProxyConfig] = ("socks5", "127.0.0.1", 10808)


def _clean_value(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config(path: str | Path = "config.txt") -> Config:
    """Load Telegram API settings from a simple key=value config file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            "config.txt پیدا نشد. فایل config.example.txt را کپی کنید و مقدارهای api_id و api_hash را داخل config.txt بگذارید."
        )

    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _clean_value(value)

    try:
        api_id = int(values["api_id"])
        api_hash = values["api_hash"]
    except KeyError as exc:
        raise ValueError("config.txt باید حداقل api_id و api_hash داشته باشد.") from exc
    except ValueError as exc:
        raise ValueError("api_id باید عدد صحیح باشد.") from exc

    source_chat = values.get("source_chat", "ahangd00ni")
    audio_command = values.get("audio_command", "آهنگ")
    download_dir = Path(values.get("download_dir", "downloaded_audios"))

    proxy_enabled = _parse_bool(values.get("proxy_enabled", "true"), default=True)
    proxy: Optional[ProxyConfig]
    if proxy_enabled:
        proxy_type = values.get("proxy_type", "socks5")
        proxy_host = values.get("proxy_host", "127.0.0.1")
        proxy_port = int(values.get("proxy_port", "10808"))
        proxy = (proxy_type, proxy_host, proxy_port)
    else:
        proxy = None

    return Config(
        api_id=api_id,
        api_hash=api_hash,
        source_chat=source_chat,
        audio_command=audio_command,
        download_dir=download_dir,
        proxy=proxy,
    )
