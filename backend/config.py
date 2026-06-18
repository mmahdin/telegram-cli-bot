from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

ProxyConfig = Tuple[str, str, int]

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    phone: str = ""
    session_name: str = "panel_session"
    source_chat: str = "ahangd00ni"
    audio_command: str = "آهنگ"
    download_dir: Path = BASE_DIR / "downloaded_audios"
    storage_dir: Path = BASE_DIR / "panel_storage"
    database_path: Path = BASE_DIR / "panel_data.sqlite3"  # kept for backward compatibility
    temp_media_dir: Path = BASE_DIR / "tmp_media_downloads"
    # When True, opening/reading chats in the panel only clears the local JSON badge.
    # It never sends Telegram read receipts, so the sender should not get a second tick.
    stealth_read: bool = True
    proxy: Optional[ProxyConfig] = None
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: tuple[str, ...] = ("*",)

    @property
    def session_path(self) -> Path:
        configured = Path(self.session_name).expanduser()
        if configured.is_absolute():
            return configured
        return BASE_DIR / configured


def _clean_value(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _candidate_config_paths(path: str | Path | None = None) -> list[Path]:
    if path is not None:
        return [Path(path).expanduser()]

    env_path = os.getenv("TELEGRAM_PANEL_CONFIG")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.extend(
        [
            BASE_DIR / "config.txt",
            PROJECT_DIR / "config.txt",
            Path.cwd() / "config.txt",
        ]
    )

    # Keep order while removing duplicates.
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate.absolute()
        if resolved not in seen:
            unique.append(candidate)
            seen.add(resolved)
    return unique


def _read_key_value_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _clean_value(value)
    return values


def load_config(path: str | Path | None = None) -> Config:
    config_path = next((p for p in _candidate_config_paths(path) if p.exists()), None)
    if config_path is None:
        searched = "\n".join(f"- {p}" for p in _candidate_config_paths(path))
        raise FileNotFoundError(
            "config.txt پیدا نشد. یکی از مسیرهای زیر را بسازید:\n" + searched
        )

    values = _read_key_value_file(config_path)

    try:
        api_id = int(values["api_id"])
        api_hash = values["api_hash"]
    except KeyError as exc:
        raise ValueError("config.txt باید حداقل api_id و api_hash داشته باشد.") from exc
    except ValueError as exc:
        raise ValueError("api_id باید عدد صحیح باشد.") from exc

    proxy_enabled = _parse_bool(values.get("proxy_enabled"), default=False)
    proxy: Optional[ProxyConfig] = None
    if proxy_enabled:
        proxy_type = values.get("proxy_type", "socks5")
        proxy_host = values.get("proxy_host", "127.0.0.1")
        try:
            proxy_port = int(values.get("proxy_port", "10808"))
        except ValueError as exc:
            raise ValueError("proxy_port باید عدد صحیح باشد.") from exc
        proxy = (proxy_type, proxy_host, proxy_port)

    download_dir = Path(values.get("download_dir", str(BASE_DIR / "downloaded_audios"))).expanduser()
    if not download_dir.is_absolute():
        download_dir = BASE_DIR / download_dir

    storage_dir = Path(values.get("storage_dir", str(BASE_DIR / "panel_storage"))).expanduser()
    if not storage_dir.is_absolute():
        storage_dir = BASE_DIR / storage_dir

    database_path = Path(values.get("database_path", str(BASE_DIR / "panel_data.sqlite3"))).expanduser()
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path

    temp_media_dir = Path(values.get("temp_media_dir", str(BASE_DIR / "tmp_media_downloads"))).expanduser()
    if not temp_media_dir.is_absolute():
        temp_media_dir = BASE_DIR / temp_media_dir

    cors_raw = values.get("cors_origins", "*")
    cors_origins = tuple(part.strip() for part in cors_raw.split(",") if part.strip()) or ("*",)

    return Config(
        api_id=api_id,
        api_hash=api_hash,
        phone=values.get("phone", ""),
        session_name=values.get("session_name", "panel_session"),
        source_chat=values.get("source_chat", "ahangd00ni"),
        audio_command=values.get("audio_command", "آهنگ"),
        download_dir=download_dir,
        storage_dir=storage_dir,
        database_path=database_path,
        temp_media_dir=temp_media_dir,
        stealth_read=_parse_bool(values.get("stealth_read"), default=True),
        proxy=proxy,
        host=values.get("host", "0.0.0.0"),
        port=int(values.get("port", "8000")),
        cors_origins=cors_origins,
    )
