from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from telethon import TelegramClient

from config import Config

TIME_PATTERN = re.compile(r"^\d+(?::\d{1,2}){1,2}$")


class MusicVoiceService:
    """Crop a source Telegram audio message and send the result as a voice reply."""

    def __init__(self, client: TelegramClient, config: Config):
        self.client = client
        self.config = config
        self.cache_dir = config.download_dir / "cache"
        self.tmp_dir = config.download_dir / "tmp"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    async def try_handle(self, event: Any, my_id: int) -> bool:
        """Return True when the event was an audio command and should not be shown in the panel."""
        if not getattr(event, "out", False):
            return False
        if event.sender_id not in {None, my_id}:
            return False

        text = (event.raw_text or "").strip()
        if not text:
            return False

        first_word = text.split(maxsplit=1)[0]
        if first_word != self.config.audio_command:
            return False

        if not event.is_reply:
            await event.reply("⚠️ باید این دستور را روی پیام کسی ریپلای کنید.")
            return True

        replied_message = await event.get_reply_message()
        if replied_message is None:
            await event.reply("❌ پیام ریپلای‌شده پیدا نشد.")
            return True

        # This must happen before any download or crop work.
        await event.delete()

        command = self._parse_command(text)
        if command is None:
            await self._reply_to_target(
                event,
                replied_message.id,
                f"⚠️ فرمت درست: {self.config.audio_command} 4191 1:09 1:17",
            )
            return True

        audio_id, start_seconds, end_seconds = command
        if start_seconds >= end_seconds:
            await self._reply_to_target(
                event,
                replied_message.id,
                "⚠️ زمان پایان باید بعد از زمان شروع باشد.",
            )
            return True

        await self._crop_and_send_voice(
            event=event,
            reply_to_message_id=replied_message.id,
            audio_id=audio_id,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        return True

    def _parse_command(self, text: str) -> tuple[int, int, int] | None:
        parts = text.split()
        if len(parts) != 4:
            return None

        command, audio_id_text, start_text, end_text = parts
        if command != self.config.audio_command:
            return None
        if not audio_id_text.isdigit():
            return None
        if not TIME_PATTERN.match(start_text) or not TIME_PATTERN.match(end_text):
            return None

        return (
            int(audio_id_text),
            self._time_to_seconds(start_text),
            self._time_to_seconds(end_text),
        )

    @staticmethod
    def _time_to_seconds(value: str) -> int:
        numbers = [int(part) for part in value.split(":")]
        if len(numbers) == 2:
            minutes, seconds = numbers
            return minutes * 60 + seconds
        if len(numbers) == 3:
            hours, minutes, seconds = numbers
            return hours * 3600 + minutes * 60 + seconds
        raise ValueError(f"Invalid time value: {value}")

    async def _crop_and_send_voice(
        self,
        event: Any,
        reply_to_message_id: int,
        audio_id: int,
        start_seconds: int,
        end_seconds: int,
    ) -> None:
        if shutil.which("ffmpeg") is None:
            await self._reply_to_target(
                event,
                reply_to_message_id,
                "❌ FFmpeg نصب نیست. در Termux: pkg install ffmpeg  |  در لینوکس: sudo apt install ffmpeg",
            )
            return

        source_audio = await self._get_or_download_source_audio(audio_id)
        if source_audio is None:
            await self._reply_to_target(
                event,
                reply_to_message_id,
                "❌ آهنگ مورد نظر پیدا نشد یا فایل صوتی نداشت.",
            )
            return

        output_path = self._new_temp_ogg_path(audio_id)
        duration = end_seconds - start_seconds

        try:
            await self._run_ffmpeg(source_audio, output_path, start_seconds, duration)
            if not output_path.exists() or output_path.stat().st_size == 0:
                await self._reply_to_target(event, reply_to_message_id, "❌ فایل voice ساخته نشد.")
                return

            await self.client.send_file(
                event.chat_id,
                str(output_path),
                voice_note=True,
                reply_to=reply_to_message_id,
            )
            print(f"Sent voice from audio_{audio_id}: {start_seconds}s to {end_seconds}s")
        except RuntimeError as exc:
            await self._reply_to_target(event, reply_to_message_id, f"❌ خطا در برش آهنگ: {exc}")
        finally:
            output_path.unlink(missing_ok=True)

    async def _get_or_download_source_audio(self, audio_id: int) -> Path | None:
        cache_path = self.cache_dir / f"audio_{audio_id}.mp3"
        if cache_path.exists() and cache_path.stat().st_size > 0:
            print(f"Using cached audio: {cache_path}")
            return cache_path

        print(f"Cache miss. Downloading source audio {audio_id}...")
        message = await self.client.get_messages(self.config.source_chat, ids=audio_id)
        if message is None or not getattr(message, "media", None):
            return None

        downloaded_path = await message.download_media(file=str(cache_path))
        if downloaded_path is None:
            return None

        path = Path(downloaded_path)
        if not path.exists() or path.stat().st_size == 0:
            return None

        if path.resolve() != cache_path.resolve():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(cache_path))
            path = cache_path

        return path

    async def _reply_to_target(self, event: Any, reply_to_message_id: int, text: str) -> None:
        await self.client.send_message(event.chat_id, text, reply_to=reply_to_message_id)

    def _new_temp_ogg_path(self, audio_id: int) -> Path:
        temp_file = tempfile.NamedTemporaryFile(
            prefix=f"voice_{audio_id}_",
            suffix=".ogg",
            dir=self.tmp_dir,
            delete=False,
        )
        temp_path = Path(temp_file.name)
        temp_file.close()
        temp_path.unlink(missing_ok=True)
        return temp_path

    @staticmethod
    async def _run_ffmpeg(
        source_path: Path,
        output_path: Path,
        start_seconds: int,
        duration_seconds: int,
    ) -> None:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-ss",
            str(start_seconds),
            "-t",
            str(duration_seconds),
            "-vn",
            "-c:a",
            "libopus",
            "-b:a",
            "64k",
            "-f",
            "ogg",
            "-y",
            str(output_path),
        ]
        result = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True)
        if result.returncode != 0:
            error = (result.stderr or "unknown ffmpeg error").strip()
            raise RuntimeError(error[:700])
