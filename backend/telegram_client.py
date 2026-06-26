from __future__ import annotations

import asyncio
import io
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from telethon import TelegramClient, events, utils
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.types import (
    Channel,
    Chat,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    Message,
    MessageMediaDocument,
    MessageMediaPhoto,
    User,
)

from config import Config, load_config
from music_voice import MusicVoiceService
from storage import JsonPanelStorage


class TelegramPanelClient:
    """Thin Telethon wrapper optimized for an HTTP + JSON-cache panel.

    UI endpoints read from JSON cache first. Explicit sync endpoints call the
    Telegram network and update that cache. No WebSocket is used.
    """

    def __init__(self) -> None:
        self.config: Config = load_config()
        self.storage = JsonPanelStorage(self.config.storage_dir)
        self.config.temp_media_dir.mkdir(parents=True, exist_ok=True)
        self.client: Optional[TelegramClient] = None
        self.me: Optional[User] = None
        self.handlers_ready = False
        self.music_service: Optional[MusicVoiceService] = None
        self._connect_lock = asyncio.Lock()
        self._dialog_sync_lock = asyncio.Lock()
        self._avatar_sync_lock = asyncio.Lock()
        self._presence_lock = asyncio.Lock()
        self._message_sync_locks: dict[int, asyncio.Lock] = {}
        self._avatar_no_photo_ids: set[int] = set()
        self._last_presence_offline_at = 0.0
        self._connecting = False
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # Connection/auth
    # ------------------------------------------------------------------
    def has_session_file(self) -> bool:
        return self.config.session_path.with_suffix(".session").exists()

    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()

    def is_connecting(self) -> bool:
        return self._connecting

    def last_error(self) -> str | None:
        return self._last_error

    async def ensure_client(self) -> TelegramClient:
        if self.client is None:
            client_kwargs: dict[str, Any] = {"proxy": self.config.proxy}
            if self.config.stealth_presence and self.config.stealth_disable_live_updates:
                # In stealth mode the HTTP panel polls dialogs/messages itself.
                # Avoid subscribing the MTProto session to live updates because
                # a permanently-live user session is more likely to refresh
                # Online / Last seen visibility.
                client_kwargs["receive_updates"] = False

            self.client = TelegramClient(
                str(self.config.session_path),
                self.config.api_id,
                self.config.api_hash,
                **client_kwargs,
            )
            self.music_service = MusicVoiceService(self.client, self.config)
        return self.client

    async def start(
        self,
        phone: str | None = None,
        code: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        async with self._connect_lock:
            self._connecting = True
            self._last_error = None
            try:
                client = await self.ensure_client()
                if not client.is_connected():
                    await client.connect()
                await self._apply_stealth_receive_updates()

                if not await client.is_user_authorized():
                    phone = phone or self.config.phone
                    if not phone:
                        return {"status": "phone_required", "message": "Phone number is required"}
                    if code is None:
                        await client.send_code_request(phone)
                        return {"status": "code_required", "message": "Verification code sent"}
                    try:
                        await client.sign_in(phone=phone, code=code)
                    except SessionPasswordNeededError:
                        if password is None:
                            return {"status": "password_required", "message": "2FA password required"}
                        await client.sign_in(password=password)

                await self._apply_stealth_receive_updates()
                await self.keep_offline("after authorization", force=True)
                self.me = await client.get_me()
                await self.keep_offline("after loading account", force=True)
                self._setup_handlers()
                return {
                    "status": "connected",
                    "message": "Connected successfully",
                    "me": await self.get_me(include_avatar=False),
                }
            except Exception as exc:
                self._last_error = str(exc)
                raise
            finally:
                self._connecting = False

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected():
            await self.client.disconnect()

    async def logout(self) -> None:
        if self.client and self.client.is_connected():
            await self.client.log_out()
        self.client = None
        self.me = None
        self.handlers_ready = False
        self.music_service = None
        self._connecting = False
        self._last_error = None
        self._last_presence_offline_at = 0.0

    async def _apply_stealth_receive_updates(self) -> None:
        """Disable live update delivery while stealth presence is enabled.

        The frontend already polls /dialogs/sync and /messages/sync. Keeping
        Telethon's live update loop disabled avoids background NewMessage/Edit
        handlers and reduces presence side effects while the user is only
        reading from the panel.
        """
        if not (self.config.stealth_presence and self.config.stealth_disable_live_updates):
            return
        if self.client is None or not self.client.is_connected():
            return
        try:
            await self.client.set_receive_updates(False)
        except Exception as exc:
            print(f"Disabling live updates failed: {exc}")

    async def keep_offline(self, reason: str = "", force: bool = False) -> None:
        """Optionally ask Telegram to keep this account offline.

        Important: account.updateStatus(offline=True) is not a harmless
        read-only operation. Telegram may treat it as a fresh "last seen now"
        timestamp. The previous implementation called it after every sync/read,
        which could make Last seen change exactly when you opened a chat.

        By default stealth_offline_refresh_seconds=0, so this method is a no-op
        and stealth is handled by disabling live updates plus avoiding read
        acknowledgements. Set stealth_offline_refresh_seconds to a positive
        value only if you deliberately want periodic offline pings.
        """
        if not self.config.stealth_presence:
            return
        if self.client is None or not self.client.is_connected():
            return

        refresh_seconds = int(getattr(self.config, "stealth_offline_refresh_seconds", 0) or 0)
        if refresh_seconds <= 0:
            return

        now = time.monotonic()
        if self._last_presence_offline_at and now - self._last_presence_offline_at < refresh_seconds:
            return

        async with self._presence_lock:
            now = time.monotonic()
            if self._last_presence_offline_at and now - self._last_presence_offline_at < refresh_seconds:
                return
            try:
                await self.client(UpdateStatusRequest(offline=True))
                self._last_presence_offline_at = time.monotonic()
            except Exception as exc:
                suffix = f" ({reason})" if reason else ""
                print(f"Stealth presence update failed{suffix}: {exc}")

    async def _after_outgoing_action(self, reason: str = "") -> None:
        """Minimize online exposure after sending/editing/deleting a message.

        Telegram may still show the account online briefly when an outgoing
        user-account action is sent. The background flag and immediate offline
        refresh reduce that window. Optional disconnect is stronger but means
        the panel must reconnect before the next Telegram network action.
        """
        await self.keep_offline(reason or "after outgoing action", force=True)
        if self.config.stealth_disconnect_after_send and self.client is not None:
            try:
                await self.client.disconnect()
            except Exception as exc:
                print(f"Stealth disconnect after send failed: {exc}")

    def _setup_handlers(self) -> None:
        if self.client is None or self.handlers_ready:
            return
        if self.config.stealth_presence and self.config.stealth_disable_live_updates:
            # No live event handlers in stealth mode. The panel still updates by
            # polling /dialogs/sync and /messages/sync, but simply opening a chat
            # will not keep a live MTProto update loop active.
            self.handlers_ready = True
            return
        self.client.add_event_handler(self._on_new_message, events.NewMessage)
        self.client.add_event_handler(self._on_message_edited, events.MessageEdited)
        self.client.add_event_handler(self._on_message_deleted, events.MessageDeleted)
        self.handlers_ready = True

    async def _get_me_entity(self) -> User:
        if self.me is None:
            if self.client is None:
                raise RuntimeError("Telegram client is not ready")
            self.me = await self.client.get_me()
        return self.me

    # ------------------------------------------------------------------
    # Event handlers update only the local JSON cache.
    # ------------------------------------------------------------------
    async def _on_new_message(self, event: Any) -> None:
        if self.client is None:
            return
        try:
            await self.keep_offline("new message update")
            me = await self._get_me_entity()
            if self.music_service and await self.music_service.try_handle(event, me.id):
                return
            if not await self._cache_event_dialog(event):
                return
            msg_data = await self.format_message(event.message)
            self.storage.upsert_message(
                msg_data,
                update_dialog=True,
                increment_unread=not bool(msg_data.get("is_outgoing")),
            )
        except Exception as exc:
            print(f"New-message handler error: {exc}")

    async def _on_message_edited(self, event: Any) -> None:
        try:
            await self.keep_offline("message edited update")
            if not await self._cache_event_dialog(event):
                return
            msg_data = await self.format_message(event.message)
            msg_data["event_type"] = "edited"
            self.storage.upsert_message(msg_data, update_dialog=True, increment_unread=False)
        except Exception as exc:
            print(f"Edit handler error: {exc}")

    async def _on_message_deleted(self, event: Any) -> None:
        try:
            await self.keep_offline("message deleted update")
            deleted_ids = list(getattr(event, "deleted_ids", []) or [])
            chat_id = getattr(event, "chat_id", None)
            self.storage.mark_deleted(deleted_ids, chat_id=chat_id)
        except Exception as exc:
            print(f"Delete handler error: {exc}")

    async def _cache_event_dialog(self, event: Any) -> bool:
        try:
            entity = await event.get_chat()
            if not self._is_supported_dialog_entity(entity):
                return False
            self.storage.upsert_dialog(self._dialog_row(entity))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Read-only cached endpoints
    # ------------------------------------------------------------------
    async def get_me(self, include_avatar: bool = False) -> Optional[dict[str, Any]]:
        if not self.is_connected():
            return None
        me = await self._get_me_entity()
        return {
            "id": me.id,
            "name": self._display_name(me),
            "username": me.username or "",
            "phone": me.phone or "",
            "avatar": await self._avatar_b64(me) if include_avatar else None,
        }

    def get_cached_dialogs(self, limit: int = 80) -> list[dict[str, Any]]:
        return self.storage.get_dialogs(limit=limit)

    def set_dialog_importance(self, chat_id: int, important: bool) -> dict[str, Any] | None:
        return self.storage.set_dialog_importance(chat_id=chat_id, important=important)

    def get_cached_messages(self, user_id: int, limit: int = 50, offset_id: int = 0, after_id: int = 0) -> list[dict[str, Any]]:
        return self.storage.get_messages(chat_id=user_id, limit=limit, offset_id=offset_id, after_id=after_id)

    # ------------------------------------------------------------------
    # Explicit HTTP sync endpoints
    # ------------------------------------------------------------------
    async def sync_dialogs(self, limit: int = 80) -> list[dict[str, Any]]:
        if self.client is None or not self.is_connected():
            return self.storage.get_dialogs(limit=limit)
        if self._dialog_sync_lock.locked():
            return self.storage.get_dialogs(limit=limit)

        async with self._dialog_sync_lock:
            try:
                await self.keep_offline("before dialog sync", force=True)
                me = await self._get_me_entity()
                dialogs = await self.client.get_dialogs(limit=limit)
                rows: list[dict[str, Any]] = []
                for dialog in dialogs:
                    entity = dialog.entity
                    if isinstance(entity, User) and entity.id == me.id:
                        continue
                    if not self._is_supported_dialog_entity(entity):
                        continue
                    last_msg = dialog.message
                    row = self._dialog_row(entity, last_msg=last_msg, unread_count=int(dialog.unread_count or 0))
                    rows.append(row)
                self.storage.upsert_dialogs(rows)
            except Exception as exc:
                self._last_error = str(exc)
                print(f"Dialog sync failed: {exc}")
            finally:
                await self.keep_offline("after dialog sync", force=True)
        return self.storage.get_dialogs(limit=limit)

    async def sync_messages(
        self,
        user_id: int,
        limit: int = 60,
        offset_id: int = 0,
        after_id: int = 0,
        mark_read: bool = False,
    ) -> list[dict[str, Any]]:
        if self.client is None or not self.is_connected():
            return self.storage.get_messages(chat_id=user_id, limit=limit, offset_id=offset_id, after_id=after_id)

        lock = self._message_sync_locks.setdefault(int(user_id), asyncio.Lock())
        if lock.locked():
            return self.storage.get_messages(chat_id=user_id, limit=limit, offset_id=offset_id, after_id=after_id)

        async with lock:
            try:
                await self.keep_offline("before message sync", force=True)
                entity = await self.client.get_entity(user_id)
                if not self._is_supported_dialog_entity(entity):
                    return self.storage.get_messages(chat_id=user_id, limit=limit, offset_id=offset_id, after_id=after_id)
                self.storage.upsert_dialog(self._dialog_row(entity))
                kwargs: dict[str, Any] = {"limit": limit}
                if offset_id:
                    kwargs["offset_id"] = offset_id
                if after_id:
                    kwargs["min_id"] = after_id
                messages = await self.client.get_messages(entity, **kwargs)
                formatted = [await self.format_message(message) for message in messages]
                self.storage.upsert_messages(formatted, update_dialog=True)
                if mark_read:
                    self.storage.mark_dialog_read(user_id)
                    if not self.config.stealth_read:
                        try:
                            await self.client.send_read_acknowledge(entity)
                        except Exception as exc:
                            print(f"Read acknowledge failed: {exc}")
            except Exception as exc:
                self._last_error = str(exc)
                print(f"Message sync failed: {exc}")
            finally:
                await self.keep_offline("after message sync", force=True)

        return self.storage.get_messages(chat_id=user_id, limit=limit, offset_id=offset_id, after_id=after_id)

    async def mark_read(self, user_id: int, telegram: bool | None = None) -> None:
        """Mark a dialog as read.

        By default this only updates the panel's JSON cache when stealth_read=True.
        Passing telegram=True explicitly sends Telegram read acknowledgement.
        """
        self.storage.mark_dialog_read(user_id)
        should_send_telegram_ack = (not self.config.stealth_read) if telegram is None else bool(telegram)
        if not should_send_telegram_ack:
            await self.keep_offline("local-only mark read")
            return
        if self.client is None or not self.is_connected():
            return
        try:
            await self.keep_offline("before explicit telegram read", force=True)
            entity = await self.client.get_entity(user_id)
            await self.client.send_read_acknowledge(entity)
            await self.keep_offline("after explicit telegram read", force=True)
        except Exception as exc:
            self._last_error = str(exc)
            print(f"Mark read failed: {exc}")

    async def mark_read_in_telegram(self, user_id: int) -> None:
        await self.mark_read(user_id, telegram=True)

    async def sync_avatars(self, limit: int = 12) -> dict[str, Any]:
        if self.client is None or not self.is_connected():
            return {"status": "offline", "downloaded": 0}
        if self._avatar_sync_lock.locked():
            return {"status": "already_running", "downloaded": 0}

        downloaded = 0
        async with self._avatar_sync_lock:
            await self.keep_offline("before avatar sync", force=True)
            for chat_id in self.storage.dialog_ids_missing_avatar(limit=limit):
                try:
                    entity = await self.client.get_entity(chat_id)
                    data = await self.client.download_profile_photo(entity, file=bytes)
                    if data:
                        self.storage.save_avatar_bytes(chat_id, data)
                        downloaded += 1
                    await asyncio.sleep(0.05)
                except Exception as exc:
                    print(f"Avatar sync skipped {chat_id}: {exc}")
            await self.keep_offline("after avatar sync", force=True)
        return {"status": "done", "downloaded": downloaded}

    # ------------------------------------------------------------------
    # Send/edit/delete/download
    # ------------------------------------------------------------------
    async def send_message(self, user_id: int, text: str, reply_to: int | None = None) -> dict[str, Any]:
        if self.client is None or not self.is_connected():
            raise RuntimeError("Not connected")
        await self.keep_offline("before send message")
        entity = await self.client.get_entity(user_id)
        if not self._is_supported_dialog_entity(entity):
            raise RuntimeError("Unsupported Telegram dialog type")
        self.storage.upsert_dialog(self._dialog_row(entity))
        msg = await self.client.send_message(
            entity,
            text,
            reply_to=reply_to,
            background=self.config.stealth_send_background,
        )
        formatted = await self.format_message(msg)
        self.storage.upsert_message(formatted, update_dialog=True)
        await self._after_outgoing_action("after send message")
        return formatted

    async def send_photo(
        self,
        user_id: int,
        file_bytes: bytes,
        filename: str,
        caption: str = "",
        reply_to: int | None = None,
    ) -> dict[str, Any]:
        if self.client is None or not self.is_connected():
            raise RuntimeError("Not connected")
        await self.keep_offline("before send photo")
        entity = await self.client.get_entity(user_id)
        if not self._is_supported_dialog_entity(entity):
            raise RuntimeError("Unsupported Telegram dialog type")
        self.storage.upsert_dialog(self._dialog_row(entity))
        upload = self._named_bytes(file_bytes, filename or "photo.jpg")
        msg = await self.client.send_file(
            entity,
            upload,
            caption=caption,
            reply_to=reply_to,
            force_document=False,
            background=self.config.stealth_send_background,
        )
        formatted = await self.format_message(msg)
        self.storage.upsert_message(formatted, update_dialog=True)
        await self._after_outgoing_action("after send photo")
        return formatted

    async def send_audio(
        self,
        user_id: int,
        file_bytes: bytes,
        filename: str,
        caption: str = "",
        reply_to: int | None = None,
    ) -> dict[str, Any]:
        if self.client is None or not self.is_connected():
            raise RuntimeError("Not connected")
        await self.keep_offline("before send audio")
        entity = await self.client.get_entity(user_id)
        if not self._is_supported_dialog_entity(entity):
            raise RuntimeError("Unsupported Telegram dialog type")
        self.storage.upsert_dialog(self._dialog_row(entity))
        upload = self._named_bytes(file_bytes, filename or "audio.mp3")
        msg = await self.client.send_file(
            entity,
            upload,
            caption=caption,
            reply_to=reply_to,
            attributes=[DocumentAttributeAudio(duration=0, voice=False, title=Path(filename).stem or filename)],
            force_document=False,
            background=self.config.stealth_send_background,
        )
        formatted = await self.format_message(msg)
        self.storage.upsert_message(formatted, update_dialog=True)
        await self._after_outgoing_action("after send audio")
        return formatted

    async def edit_message(self, user_id: int, message_id: int, new_text: str) -> dict[str, Any]:
        if self.client is None or not self.is_connected():
            raise RuntimeError("Not connected")
        await self.keep_offline("before edit message")
        entity = await self.client.get_entity(user_id)
        if not self._is_supported_dialog_entity(entity):
            raise RuntimeError("Unsupported Telegram dialog type")
        msg = await self.client.edit_message(entity, message_id, new_text)
        formatted = await self.format_message(msg)
        self.storage.upsert_message(formatted, update_dialog=True)
        await self._after_outgoing_action("after edit message")
        return formatted

    async def delete_message(self, user_id: int, message_id: int) -> bool:
        if self.client is None or not self.is_connected():
            raise RuntimeError("Not connected")
        await self.keep_offline("before delete message")
        entity = await self.client.get_entity(user_id)
        if not self._is_supported_dialog_entity(entity):
            raise RuntimeError("Unsupported Telegram dialog type")
        await self.client.delete_messages(entity, [message_id])
        self.storage.mark_deleted([message_id], chat_id=user_id)
        await self._after_outgoing_action("after delete message")
        return True

    async def download_message_media(self, user_id: int, message_id: int) -> tuple[Path, str, str]:
        if self.client is None or not self.is_connected():
            raise RuntimeError("Not connected")
        await self.keep_offline("before media download", force=True)
        entity = await self.client.get_entity(user_id)
        if not self._is_supported_dialog_entity(entity):
            raise RuntimeError("Unsupported Telegram dialog type")
        message = await self.client.get_messages(entity, ids=message_id)
        if message is None or not getattr(message, "media", None):
            raise FileNotFoundError("Message media not found")
        media = await self._media_meta(message)
        if media is None:
            raise FileNotFoundError("Unsupported media")

        filename = self._safe_filename(media.get("filename") or f"telegram-media-{message_id}")
        suffix = Path(filename).suffix or mimetypes.guess_extension(media.get("mime") or "") or ""
        target = self.config.temp_media_dir / f"{user_id}_{message_id}_{uuid.uuid4().hex}{suffix}"
        downloaded = await self.client.download_media(message.media, file=str(target))
        path = Path(downloaded) if downloaded else target
        if not path.exists() or path.stat().st_size == 0:
            raise FileNotFoundError("Unable to download media")
        await self.keep_offline("after media download", force=True)
        mime = media.get("mime") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return path, mime, filename

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------
    async def format_message(self, msg: Message) -> dict[str, Any]:
        chat_id = self._message_chat_id(msg)
        sender_info = await self._sender_info(msg)
        media_info = await self._media_meta(msg) if getattr(msg, "media", None) else None
        return {
            "id": msg.id,
            "event_type": "new_message",
            "chat_id": chat_id,
            "chat_type": self._message_chat_type(msg),
            "sender_id": msg.sender_id,
            "sender_name": sender_info.get("name"),
            "sender_username": sender_info.get("username"),
            "sender_avatar": sender_info.get("avatar"),
            "is_outgoing": bool(msg.out),
            "text": msg.message or "",
            "date": msg.date.isoformat() if msg.date else None,
            "media": media_info,
            "reply_to_msg_id": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
            "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
        }

    async def _media_meta(self, msg: Message) -> Optional[dict[str, Any]]:
        chat_id = self._message_chat_id(msg)
        if isinstance(msg.media, MessageMediaPhoto):
            return {
                "type": "photo",
                "filename": f"photo_{msg.id}.jpg",
                "mime": "image/jpeg",
                "size": None,
                "is_voice": False,
                "data": None,
                "download_only": True,
                "download_url": f"/messages/{chat_id}/{msg.id}/media",
            }
        if isinstance(msg.media, MessageMediaDocument):
            doc = msg.media.document
            mime = doc.mime_type or "application/octet-stream"
            filename = f"file_{msg.id}"
            is_audio = False
            is_voice = False
            is_video = mime.startswith("video/")
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeAudio):
                    is_audio = True
                    is_voice = bool(attr.voice)
                    if getattr(attr, "title", None):
                        filename = str(attr.title)
                elif isinstance(attr, DocumentAttributeVideo):
                    is_video = True
                elif isinstance(attr, DocumentAttributeFilename):
                    filename = attr.file_name
            if "." not in filename:
                filename = f"{filename}{mimetypes.guess_extension(mime) or ''}"
            media_type = "voice" if is_voice else "audio" if is_audio else "video" if is_video else "document"
            return {
                "type": media_type,
                "filename": filename,
                "mime": mime,
                "size": getattr(doc, "size", None),
                "is_voice": is_voice,
                "data": None,
                "download_only": True,
                "download_url": f"/messages/{chat_id}/{msg.id}/media",
            }
        return None

    def storage_stats(self) -> dict[str, int | str]:
        return self.storage.stats()

    def avatar_path(self, user_id: int) -> Path:
        return self.storage.avatar_path(user_id)

    def _message_chat_id(self, msg: Message) -> int:
        peer = getattr(msg, "peer_id", None)
        if peer is not None:
            try:
                return int(utils.get_peer_id(peer))
            except Exception:
                pass
        chat_id = getattr(msg, "chat_id", None)
        if chat_id is not None:
            return int(chat_id)
        return int(msg.sender_id or 0)

    def _message_chat_type(self, msg: Message) -> str:
        peer = getattr(msg, "peer_id", None)
        if hasattr(peer, "user_id"):
            return "private"
        if hasattr(peer, "chat_id") or hasattr(peer, "channel_id"):
            return "group"
        return "private"

    async def _sender_info(self, msg: Message) -> dict[str, str | None]:
        try:
            sender = getattr(msg, "sender", None) or await msg.get_sender()
        except Exception:
            sender = None
        if sender is None:
            return {"name": None, "username": None, "avatar": None}

        sender_id = self._entity_storage_id(sender)
        should_cache_sender_avatar = self._message_chat_type(msg) == "group" and not bool(msg.out)
        if sender_id is not None and should_cache_sender_avatar:
            await self._ensure_avatar_cached(sender_id, sender)
        return {
            "name": self._display_name(sender),
            "username": getattr(sender, "username", None) or None,
            "avatar": self.storage.avatar_url(sender_id) if sender_id is not None else None,
        }

    def _entity_storage_id(self, entity: Any) -> int | None:
        try:
            return int(utils.get_peer_id(entity))
        except Exception:
            raw_id = getattr(entity, "id", None)
            return int(raw_id) if raw_id is not None else None

    async def _ensure_avatar_cached(self, storage_id: int, entity: Any) -> None:
        if self.client is None:
            return
        storage_id = int(storage_id)
        if storage_id in self._avatar_no_photo_ids or self.storage.avatar_path(storage_id).exists():
            return
        try:
            await self.keep_offline("before sender avatar download")
            data = await self.client.download_profile_photo(entity, file=bytes)
            if data:
                self.storage.save_avatar_bytes(storage_id, data)
            else:
                self._avatar_no_photo_ids.add(storage_id)
            await self.keep_offline("after sender avatar download")
        except Exception:
            self._avatar_no_photo_ids.add(storage_id)

    def _dialog_row(
        self,
        entity: User | Chat | Channel,
        last_msg: Message | None = None,
        unread_count: int | None = None,
    ) -> dict[str, Any]:
        chat_id = int(utils.get_peer_id(entity))
        chat_type = self._dialog_type(entity)
        return {
            "id": chat_id,
            "name": self._display_name(entity),
            "username": getattr(entity, "username", None) or "",
            "phone": getattr(entity, "phone", None) or "",
            "is_bot": isinstance(entity, User) and bool(entity.bot),
            "is_group": chat_type == "group",
            "chat_type": chat_type,
            "last_message": self._last_message_preview(last_msg) if last_msg is not None else None,
            "last_message_time": last_msg.date.isoformat() if last_msg and last_msg.date else None,
            "unread_count": int(unread_count) if unread_count is not None else None,
            "avatar": self.storage.avatar_url(chat_id),
        }

    @staticmethod
    def _is_supported_dialog_entity(entity: Any) -> bool:
        if isinstance(entity, User):
            return True
        if isinstance(entity, Chat):
            return True
        if isinstance(entity, Channel):
            return bool(getattr(entity, "megagroup", False) or getattr(entity, "gigagroup", False))
        return False

    @staticmethod
    def _dialog_type(entity: Any) -> str:
        if isinstance(entity, User):
            return "bot" if bool(entity.bot) else "private"
        return "group"

    async def _avatar_b64(self, entity: User) -> Optional[str]:
        # Used only when explicitly requested for the logged-in user. Dialog
        # avatars are served as small local files via /avatars/{id}.
        if self.client is None:
            return None
        try:
            await self.keep_offline("before account avatar download")
            data = await self.client.download_profile_photo(entity, file=bytes)
            if data:
                import base64
                encoded = "data:image/jpeg;base64," + base64.b64encode(data).decode()
                await self.keep_offline("after account avatar download")
                return encoded
        except Exception:
            return None
        return None

    @staticmethod
    def _display_name(entity: User | Chat | Channel) -> str:
        if isinstance(entity, User):
            name = " ".join(part for part in [entity.first_name, entity.last_name] if part)
            return name or entity.username or entity.phone or str(entity.id)
        title = getattr(entity, "title", None)
        username = getattr(entity, "username", None)
        return title or username or str(getattr(entity, "id", ""))

    @staticmethod
    def _last_message_preview(msg: Message | None) -> str:
        if msg is None:
            return ""
        if msg.message:
            return msg.message[:120]
        if isinstance(msg.media, MessageMediaPhoto):
            return "[عکس]"
        if isinstance(msg.media, MessageMediaDocument):
            mime = msg.media.document.mime_type or ""
            if mime.startswith("video/"):
                return "[ویدیو]"
            if mime.startswith("audio/"):
                return "[آهنگ]"
            return "[فایل]"
        return "[media]"

    @staticmethod
    def _named_bytes(file_bytes: bytes, filename: str) -> io.BytesIO:
        upload = io.BytesIO(file_bytes)
        upload.name = filename
        upload.seek(0)
        return upload

    @staticmethod
    def _safe_filename(filename: str) -> str:
        cleaned = "".join(ch for ch in filename if ch.isalnum() or ch in {".", "_", "-", " ", "(" , ")"}).strip()
        return cleaned or "telegram-media"


_panel = TelegramPanelClient()

# Module-level helpers used by FastAPI routes.
has_session_file = _panel.has_session_file
is_connected = _panel.is_connected
is_connecting = _panel.is_connecting
last_error = _panel.last_error
start_client = _panel.start
disconnect = _panel.disconnect
logout = _panel.logout
get_me = _panel.get_me
get_cached_dialogs = _panel.get_cached_dialogs
set_dialog_importance = _panel.set_dialog_importance
sync_dialogs = _panel.sync_dialogs
get_cached_messages = _panel.get_cached_messages
sync_messages = _panel.sync_messages
mark_read = _panel.mark_read
mark_read_in_telegram = _panel.mark_read_in_telegram
sync_avatars = _panel.sync_avatars
send_message = _panel.send_message
send_photo = _panel.send_photo
send_audio = _panel.send_audio
edit_message = _panel.edit_message
delete_message = _panel.delete_message
download_message_media = _panel.download_message_media
storage_stats = _panel.storage_stats
avatar_path = _panel.avatar_path
