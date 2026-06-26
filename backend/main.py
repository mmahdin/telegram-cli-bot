from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import telegram_client as tg
from config import load_config

_auto_connect_task: asyncio.Task | None = None
_avatar_sync_task: asyncio.Task | None = None


def auto_connect_pending() -> bool:
    return _auto_connect_task is not None and not _auto_connect_task.done()


def avatar_sync_pending() -> bool:
    return _avatar_sync_task is not None and not _avatar_sync_task.done()


async def _auto_connect_from_session() -> None:
    if not tg.has_session_file():
        print("No Telegram session file found. Login from the panel first.")
        return
    print("Telegram auto-connect: starting in background")
    try:
        result = await tg.start_client()
        print(f"Telegram auto-connect: {result.get('status')}")
        if result.get("status") == "connected":
            # Fill the JSON cache in the background. The server is already up.
            asyncio.create_task(tg.sync_dialogs(limit=80))
    except Exception as exc:
        print(f"Telegram auto-connect failed: {exc}")


async def _run_avatar_sync(limit: int = 12) -> None:
    try:
        await tg.sync_avatars(limit=limit)
    except Exception as exc:
        print(f"Avatar background sync failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _auto_connect_task
    _auto_connect_task = asyncio.create_task(_auto_connect_from_session())
    try:
        yield
    finally:
        for task in [_auto_connect_task, _avatar_sync_task]:
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await tg.disconnect()


cfg = load_config()
app = FastAPI(title="Telegram Panel API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cfg.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    phone: Optional[str] = None
    code: Optional[str] = None
    password: Optional[str] = None


class SendMessageRequest(BaseModel):
    text: str = Field(min_length=1)
    reply_to: Optional[int] = None


class DialogImportanceRequest(BaseModel):
    important: bool


class EditMessageRequest(BaseModel):
    new_text: str = Field(min_length=1)


def require_connection() -> None:
    if not tg.is_connected():
        raise HTTPException(status_code=401, detail="Not connected to Telegram")


@app.get("/")
async def root():
    return {"status": "ok", "service": "telegram-panel-api", "transport": "http-only"}


@app.get("/health")
async def health():
    return {
        "ok": True,
        "transport": "http-only",
        "telegram_connected": tg.is_connected(),
        "telegram_connecting": tg.is_connecting() or auto_connect_pending(),
        "avatar_syncing": avatar_sync_pending(),
        "stealth_read": cfg.stealth_read,
        "stealth_presence": cfg.stealth_presence,
        "stealth_disable_live_updates": cfg.stealth_disable_live_updates,
        "stealth_offline_refresh_seconds": cfg.stealth_offline_refresh_seconds,
        "stealth_send_background": cfg.stealth_send_background,
        "stealth_disconnect_after_send": cfg.stealth_disconnect_after_send,
        "last_error": tg.last_error(),
    }


@app.post("/auth/login")
async def login(request: LoginRequest):
    try:
        result = await tg.start_client(
            phone=request.phone,
            code=request.code,
            password=request.password,
        )
        if result.get("status") == "connected":
            asyncio.create_task(tg.sync_dialogs(limit=80))
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/auth/connect")
async def connect_existing_session():
    if not tg.has_session_file():
        raise HTTPException(status_code=404, detail="No Telegram session file found")
    if tg.is_connected():
        return {"status": "connected", "me": await tg.get_me(include_avatar=False)}
    if tg.is_connecting() or auto_connect_pending():
        return {"status": "connecting"}
    asyncio.create_task(_auto_connect_from_session())
    return {"status": "connecting"}


@app.get("/auth/status")
async def auth_status():
    me = None
    if tg.is_connected():
        try:
            me = await tg.get_me(include_avatar=False)
        except Exception:
            me = None
    return {
        "connected": tg.is_connected(),
        "connecting": tg.is_connecting() or auto_connect_pending(),
        "has_session": tg.has_session_file(),
        "last_error": tg.last_error(),
        "stealth_read": cfg.stealth_read,
        "stealth_presence": cfg.stealth_presence,
        "stealth_disable_live_updates": cfg.stealth_disable_live_updates,
        "stealth_offline_refresh_seconds": cfg.stealth_offline_refresh_seconds,
        "stealth_send_background": cfg.stealth_send_background,
        "stealth_disconnect_after_send": cfg.stealth_disconnect_after_send,
        "me": me,
    }


@app.post("/auth/logout")
async def logout():
    await tg.logout()
    return {"status": "logged_out"}


# -------------------------------------------------------------------------
# Fast cache-first HTTP API
# -------------------------------------------------------------------------
@app.get("/dialogs")
async def get_dialogs(limit: int = 80):
    # Cache only. This must stay fast even when Telegram is slow.
    return {"dialogs": tg.get_cached_dialogs(limit=limit), "source": "cache"}


@app.post("/dialogs/sync")
async def sync_dialogs(limit: int = 80):
    require_connection()
    dialogs = await tg.sync_dialogs(limit=limit)
    return {"dialogs": dialogs, "source": "telegram"}


@app.patch("/dialogs/{chat_id}/importance")
async def set_dialog_importance(chat_id: int, request: DialogImportanceRequest):
    dialog = tg.set_dialog_importance(chat_id=chat_id, important=request.important)
    if not dialog:
        raise HTTPException(status_code=404, detail="Dialog not found in local cache")
    return {"dialog": dialog}


@app.get("/messages/{user_id}")
async def get_messages(user_id: int, limit: int = 50, offset_id: int = 0, after_id: int = 0):
    # Cache only. The frontend uses this for instant rendering.
    return {
        "messages": tg.get_cached_messages(user_id=user_id, limit=limit, offset_id=offset_id, after_id=after_id),
        "source": "cache",
    }


@app.post("/messages/{user_id}/sync")
async def sync_messages(
    user_id: int,
    limit: int = 60,
    offset_id: int = 0,
    after_id: int = 0,
    mark_read: bool = False,
):
    require_connection()
    messages = await tg.sync_messages(
        user_id=user_id,
        limit=limit,
        offset_id=offset_id,
        after_id=after_id,
        mark_read=mark_read,
    )
    return {"messages": messages, "source": "telegram"}


@app.post("/messages/{user_id}/read")
async def mark_messages_read(user_id: int):
    # Privacy-first default: this clears only the panel JSON badge.
    # It does not send Telegram read acknowledgement, so the sender should not see a second tick.
    await tg.mark_read(user_id, telegram=False)
    return {
        "status": "ok",
        "telegram_ack_sent": False,
        "stealth_read": cfg.stealth_read,
        "stealth_presence": cfg.stealth_presence,
    }


@app.post("/messages/{user_id}/telegram-read")
async def mark_messages_read_in_telegram(user_id: int):
    # Explicit opt-in endpoint for when you intentionally want Telegram itself to mark the chat as read.
    require_connection()
    await tg.mark_read_in_telegram(user_id)
    return {"status": "ok", "telegram_ack_sent": True}


@app.get("/messages/{user_id}/{message_id}/media")
async def get_message_media(user_id: int, message_id: int, background_tasks: BackgroundTasks):
    require_connection()
    try:
        path, mime, filename = await tg.download_message_media(user_id=user_id, message_id=message_id)
        background_tasks.add_task(_safe_unlink, path)
        return FileResponse(path=path, media_type=mime, filename=filename, background=background_tasks)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/avatars/sync")
async def sync_avatars(limit: int = 12):
    global _avatar_sync_task
    require_connection()
    if _avatar_sync_task and not _avatar_sync_task.done():
        return {"status": "already_running"}
    _avatar_sync_task = asyncio.create_task(_run_avatar_sync(limit=limit))
    return {"status": "started"}


@app.get("/avatars/{user_id}")
async def get_avatar(user_id: int):
    path = tg.avatar_path(user_id)
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Avatar not cached yet")
    return FileResponse(path=path, media_type="image/jpeg")


# -------------------------------------------------------------------------
# Mutations
# -------------------------------------------------------------------------
@app.post("/messages/{user_id}/send")
async def send_message(user_id: int, request: SendMessageRequest):
    require_connection()
    try:
        return {"message": await tg.send_message(user_id=user_id, text=request.text, reply_to=request.reply_to)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/messages/{user_id}/send-photo")
async def send_photo(
    user_id: int,
    file: UploadFile = File(...),
    caption: str = Form(""),
    reply_to: Optional[int] = Form(None),
):
    require_connection()
    try:
        file_bytes = await file.read()
        return {
            "message": await tg.send_photo(
                user_id=user_id,
                file_bytes=file_bytes,
                filename=file.filename or "photo.jpg",
                caption=caption,
                reply_to=reply_to,
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/messages/{user_id}/send-audio")
async def send_audio(
    user_id: int,
    file: UploadFile = File(...),
    caption: str = Form(""),
    reply_to: Optional[int] = Form(None),
):
    require_connection()
    try:
        file_bytes = await file.read()
        return {
            "message": await tg.send_audio(
                user_id=user_id,
                file_bytes=file_bytes,
                filename=file.filename or "audio.mp3",
                caption=caption,
                reply_to=reply_to,
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/messages/{user_id}/{message_id}")
async def edit_message(user_id: int, message_id: int, request: EditMessageRequest):
    require_connection()
    try:
        return {
            "message": await tg.edit_message(
                user_id=user_id,
                message_id=message_id,
                new_text=request.new_text,
            )
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/messages/{user_id}/{message_id}")
async def delete_message(user_id: int, message_id: int):
    require_connection()
    try:
        await tg.delete_message(user_id=user_id, message_id=message_id)
        return {"status": "deleted"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _safe_unlink(path) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"Temp media cleanup failed: {exc}")


@app.get("/storage/stats")
async def storage_stats():
    return tg.storage_stats()


if __name__ == "__main__":
    uvicorn.run("main:app", host=cfg.host, port=cfg.port, reload=False)
