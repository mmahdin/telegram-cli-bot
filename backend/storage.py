from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Iterable


class JsonPanelStorage:
    """JSON-file storage for the Telegram panel.

    The storage intentionally keeps only dialog/message metadata. It never stores
    media bytes, base64 previews, photos, videos, audio, or documents. Media is
    downloaded only when the explicit download endpoint is called.
    """

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.chats_dir = self.root_dir / "chats"
        self.avatars_dir = self.root_dir / "avatars"
        self.dialogs_path = self.root_dir / "dialogs.json"
        self.meta_path = self.root_dir / "meta.json"
        self._lock = RLock()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.chats_dir.mkdir(parents=True, exist_ok=True)
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        if not self.dialogs_path.exists():
            self._write_json(self.dialogs_path, {"dialogs": {}})
        if not self.meta_path.exists():
            self._write_json(self.meta_path, {"version": 1})

    # ---------------------------------------------------------------------
    # Dialogs
    # ---------------------------------------------------------------------
    def upsert_dialog(self, dialog: dict[str, Any]) -> None:
        if not dialog.get("id"):
            return
        chat_id = int(dialog["id"])
        with self._lock:
            data = self._read_dialogs_unlocked()
            dialogs = data.setdefault("dialogs", {})
            old = dialogs.get(str(chat_id), {})

            avatar = dialog.get("avatar") or old.get("avatar") or self.avatar_url(chat_id)
            unread = dialog.get("unread_count")
            if unread is None:
                unread = old.get("unread_count", 0)
            if old.get("locally_read"):
                old_time = old.get("last_message_time") or ""
                new_time = dialog.get("last_message_time") or old_time
                # Telegram can need a moment to reflect read acknowledgements.
                # Keep the local badge cleared until a genuinely newer message appears.
                if not new_time or new_time <= old_time:
                    unread = 0

            chat_type = dialog.get("chat_type") or old.get("chat_type") or ("bot" if dialog.get("is_bot") or old.get("is_bot") else "private")
            is_bot = bool(dialog.get("is_bot", old.get("is_bot", False)))
            is_group = bool(dialog.get("is_group", old.get("is_group", False))) or chat_type == "group"
            if is_group:
                chat_type = "group"

            is_important = bool(dialog.get("is_important", old.get("is_important", False)))

            merged = {
                "id": chat_id,
                "name": dialog.get("name") or old.get("name") or "",
                "username": dialog.get("username") or old.get("username") or "",
                "phone": dialog.get("phone") or old.get("phone") or "",
                "is_bot": is_bot,
                "is_group": is_group,
                "chat_type": chat_type,
                "is_important": is_important,
                "last_message": dialog.get("last_message") if dialog.get("last_message") is not None else old.get("last_message", ""),
                "last_message_time": dialog.get("last_message_time") or old.get("last_message_time"),
                "unread_count": int(unread or 0),
                "avatar": avatar,
                "locally_read": bool(old.get("locally_read", False)) and int(unread or 0) == 0,
                "updated_at": self._max_iso(dialog.get("last_message_time"), old.get("updated_at")),
            }
            dialogs[str(chat_id)] = merged
            self._write_json(self.dialogs_path, data)

    def upsert_dialogs(self, dialogs: Iterable[dict[str, Any]]) -> None:
        for dialog in dialogs:
            self.upsert_dialog(dialog)

    def get_dialogs(self, limit: int = 80) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read_dialogs_unlocked()
            rows = list(data.get("dialogs", {}).values())
        rows.sort(key=lambda d: d.get("last_message_time") or d.get("updated_at") or "", reverse=True)
        return [self._public_dialog(row) for row in rows[: int(limit)]]

    def get_dialog(self, chat_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._read_dialogs_unlocked().get("dialogs", {}).get(str(int(chat_id)))
        return self._public_dialog(row) if row else None

    def set_dialog_importance(self, chat_id: int, important: bool) -> dict[str, Any] | None:
        chat_id = int(chat_id)
        with self._lock:
            data = self._read_dialogs_unlocked()
            dialogs = data.setdefault("dialogs", {})
            row = dialogs.get(str(chat_id))
            if not row:
                return None
            row["is_important"] = bool(important)
            dialogs[str(chat_id)] = row
            self._write_json(self.dialogs_path, data)
        return self.get_dialog(chat_id)

    def mark_dialog_read(self, chat_id: int) -> None:
        chat_id = int(chat_id)
        with self._lock:
            data = self._read_dialogs_unlocked()
            dialogs = data.setdefault("dialogs", {})
            row = dialogs.get(str(chat_id))
            if row:
                row["unread_count"] = 0
                row["locally_read"] = True
                dialogs[str(chat_id)] = row
                self._write_json(self.dialogs_path, data)

    def update_dialog_from_message(self, message: dict[str, Any], increment_unread: bool = False) -> None:
        chat_id = message.get("chat_id") or message.get("sender_id")
        if not chat_id:
            return
        chat_id = int(chat_id)
        with self._lock:
            data = self._read_dialogs_unlocked()
            dialogs = data.setdefault("dialogs", {})
            old = dialogs.get(str(chat_id), {"id": chat_id})
            old_time = old.get("last_message_time") or ""
            msg_time = message.get("date") or ""
            if msg_time and old_time and msg_time < old_time:
                # Older history sync should not overwrite the dialog preview.
                pass
            else:
                old["last_message"] = self._message_preview(message)
                old["last_message_time"] = message.get("date") or old.get("last_message_time")
            if increment_unread and not message.get("is_outgoing"):
                old["unread_count"] = int(old.get("unread_count") or 0) + 1
                old["locally_read"] = False
            old["avatar"] = old.get("avatar") or self.avatar_url(chat_id)
            if message.get("chat_type") and not old.get("chat_type"):
                old["chat_type"] = message.get("chat_type")
                old["is_group"] = message.get("chat_type") == "group"
            dialogs[str(chat_id)] = old
            self._write_json(self.dialogs_path, data)

    def dialog_ids_missing_avatar(self, limit: int = 20) -> list[int]:
        with self._lock:
            dialogs = list(self._read_dialogs_unlocked().get("dialogs", {}).values())
        missing: list[int] = []
        for dialog in dialogs:
            chat_id = int(dialog.get("id") or 0)
            if not chat_id:
                continue
            if not self.avatar_path(chat_id).exists():
                missing.append(chat_id)
            if len(missing) >= limit:
                break
        return missing

    # ---------------------------------------------------------------------
    # Messages
    # ---------------------------------------------------------------------
    def upsert_message(self, message: dict[str, Any], update_dialog: bool = True, increment_unread: bool = False) -> None:
        chat_id = message.get("chat_id") or message.get("sender_id")
        msg_id = message.get("id")
        if not chat_id or not msg_id:
            return
        chat_id = int(chat_id)
        msg_id = int(msg_id)

        clean = self._sanitize_message(message)
        with self._lock:
            data = self._read_chat_unlocked(chat_id)
            messages = data.setdefault("messages", {})
            old = messages.get(str(msg_id), {})
            messages[str(msg_id)] = {**old, **clean, "deleted": False}
            self._write_json(self._chat_path(chat_id), data)

        if update_dialog:
            self.update_dialog_from_message(clean, increment_unread=increment_unread)

    def upsert_messages(self, messages: Iterable[dict[str, Any]], update_dialog: bool = True) -> None:
        for message in messages:
            self.upsert_message(message, update_dialog=update_dialog, increment_unread=False)

    def get_messages(self, chat_id: int, limit: int = 50, offset_id: int = 0, after_id: int = 0) -> list[dict[str, Any]]:
        chat_id = int(chat_id)
        limit = max(1, min(int(limit), 200))
        with self._lock:
            data = self._read_chat_unlocked(chat_id)
            rows = [m for m in data.get("messages", {}).values() if not m.get("deleted")]

        if after_id:
            selected = [m for m in rows if int(m.get("id") or 0) > int(after_id)]
            selected.sort(key=lambda m: int(m.get("id") or 0))
            return [self._public_message(m) for m in selected[:limit]]

        if offset_id:
            selected = [m for m in rows if int(m.get("id") or 0) < int(offset_id)]
        else:
            selected = rows
        selected.sort(key=lambda m: int(m.get("id") or 0), reverse=True)
        return [self._public_message(m) for m in selected[:limit]]

    def newest_message_id(self, chat_id: int) -> int:
        with self._lock:
            rows = self._read_chat_unlocked(int(chat_id)).get("messages", {}).values()
        ids = [int(m.get("id") or 0) for m in rows if not m.get("deleted")]
        return max(ids) if ids else 0

    def oldest_message_id(self, chat_id: int) -> int:
        with self._lock:
            rows = self._read_chat_unlocked(int(chat_id)).get("messages", {}).values()
        ids = [int(m.get("id") or 0) for m in rows if not m.get("deleted")]
        return min(ids) if ids else 0

    def mark_deleted(self, message_ids: Iterable[int], chat_id: int | None = None) -> None:
        ids = {str(int(mid)) for mid in message_ids if mid is not None}
        if not ids:
            return
        with self._lock:
            chat_ids = [int(chat_id)] if chat_id is not None else self._all_chat_ids_unlocked()
            for cid in chat_ids:
                data = self._read_chat_unlocked(cid)
                changed = False
                for msg_id in ids:
                    if msg_id in data.get("messages", {}):
                        data["messages"][msg_id]["deleted"] = True
                        changed = True
                if changed:
                    self._write_json(self._chat_path(cid), data)

    # ---------------------------------------------------------------------
    # Avatars and stats
    # ---------------------------------------------------------------------
    def avatar_path(self, chat_id: int) -> Path:
        return self.avatars_dir / f"{int(chat_id)}.jpg"

    def avatar_url(self, chat_id: int) -> str | None:
        path = self.avatar_path(chat_id)
        if not path.exists():
            return None
        version = int(path.stat().st_mtime)
        return f"/avatars/{int(chat_id)}?v={version}"

    def save_avatar_bytes(self, chat_id: int, data: bytes) -> None:
        if not data:
            return
        path = self.avatar_path(chat_id)
        self._atomic_write_bytes(path, data)
        with self._lock:
            dialogs_data = self._read_dialogs_unlocked()
            row = dialogs_data.setdefault("dialogs", {}).get(str(int(chat_id)))
            if row:
                row["avatar"] = self.avatar_url(chat_id)
                self._write_json(self.dialogs_path, dialogs_data)

    def stats(self) -> dict[str, int | str]:
        dialogs = self.get_dialogs(limit=1_000_000)
        message_count = 0
        with self._lock:
            for cid in self._all_chat_ids_unlocked():
                message_count += len([m for m in self._read_chat_unlocked(cid).get("messages", {}).values() if not m.get("deleted")])
        return {
            "dialogs": len(dialogs),
            "messages": message_count,
            "storage_dir": str(self.root_dir),
            "avatars_dir": str(self.avatars_dir),
        }

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _chat_path(self, chat_id: int) -> Path:
        return self.chats_dir / f"{int(chat_id)}.json"

    def _read_dialogs_unlocked(self) -> dict[str, Any]:
        return self._read_json(self.dialogs_path, {"dialogs": {}})

    def _read_chat_unlocked(self, chat_id: int) -> dict[str, Any]:
        return self._read_json(self._chat_path(chat_id), {"chat_id": int(chat_id), "messages": {}})

    def _all_chat_ids_unlocked(self) -> list[int]:
        ids: set[int] = set()
        for path in self.chats_dir.glob("*.json"):
            try:
                ids.add(int(path.stem))
            except ValueError:
                continue
        ids.update(int(d.get("id")) for d in self._read_dialogs_unlocked().get("dialogs", {}).values() if d.get("id"))
        return sorted(ids)

    def _read_json(self, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            if not path.exists():
                return dict(fallback)
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return dict(fallback)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)

    def _atomic_write_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def _sanitize_message(self, message: dict[str, Any]) -> dict[str, Any]:
        media = message.get("media")
        if isinstance(media, dict):
            media = dict(media)
            media["data"] = None
        else:
            media = None
        return {
            "id": int(message.get("id") or 0),
            "event_type": message.get("event_type") or "new_message",
            "chat_id": int(message.get("chat_id") or message.get("sender_id") or 0),
            "sender_id": message.get("sender_id"),
            "sender_name": message.get("sender_name"),
            "sender_username": message.get("sender_username"),
            "sender_avatar": message.get("sender_avatar"),
            "chat_type": message.get("chat_type") or "private",
            "is_outgoing": bool(message.get("is_outgoing")),
            "text": message.get("text") or "",
            "date": message.get("date"),
            "media": media,
            "reply_to_msg_id": message.get("reply_to_msg_id"),
            "edit_date": message.get("edit_date"),
        }

    def _public_dialog(self, row: dict[str, Any]) -> dict[str, Any]:
        row = row or {}
        chat_id = int(row.get("id") or 0)
        avatar = self.avatar_url(chat_id) if chat_id else None
        return {
            "id": chat_id,
            "name": row.get("name") or "",
            "username": row.get("username") or "",
            "phone": row.get("phone") or "",
            "is_bot": bool(row.get("is_bot")),
            "is_group": bool(row.get("is_group")) or row.get("chat_type") == "group",
            "chat_type": row.get("chat_type") or ("bot" if row.get("is_bot") else "private"),
            "is_important": bool(row.get("is_important", False)),
            "last_message": row.get("last_message") or "",
            "last_message_time": row.get("last_message_time"),
            "unread_count": int(row.get("unread_count") or 0),
            "avatar": avatar,
        }

    def _public_message(self, row: dict[str, Any]) -> dict[str, Any]:
        msg = self._sanitize_message(row)
        if isinstance(msg.get("media"), dict):
            msg["media"]["data"] = None
        sender_id = msg.get("sender_id")
        if sender_id and not msg.get("sender_avatar"):
            msg["sender_avatar"] = self.avatar_url(int(sender_id))
        return msg

    def _message_preview(self, message: dict[str, Any]) -> str:
        text = (message.get("text") or "").strip()
        if text:
            return text[:120]
        media = message.get("media")
        if isinstance(media, dict):
            media_type = media.get("type")
            return {
                "photo": "[عکس]",
                "video": "[ویدیو]",
                "voice": "[ویس]",
                "audio": "[آهنگ]",
                "document": "[فایل]",
            }.get(media_type, "[media]")
        return ""

    @staticmethod
    def _max_iso(a: str | None, b: str | None) -> str | None:
        if a and b:
            return max(a, b)
        return a or b


# Backward compatible import name for older modules.
PanelStorage = JsonPanelStorage
