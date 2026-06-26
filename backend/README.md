# Backend

```bash
cp config.example.txt config.txt
# Fill api_id/api_hash/phone in config.txt
pip install -r requirements.txt
python main.py
```

## Storage model

The panel stores chat metadata in JSON files under `panel_storage/`:

- dialogs
- message text
- sender id / chat id
- message date / edit date
- reply id
- media metadata such as type, filename, mime type, size, and download URL

It does **not** store media bytes, base64 previews, photos, videos, voices, audios, or documents. Media is downloaded only when the user clicks the download button in the chat UI. The backend downloads the requested media to a temporary file and deletes that temporary file after the HTTP response is sent.

The legacy `آهنگ ...` reply feature is still handled by `music_voice.py` and uses `download_dir` only for the source audio cache used by that feature.

Read and presence privacy:

- `stealth_read=true` is the default. Opening a chat in the panel only clears the local JSON unread badge. It does **not** call Telethon `send_read_acknowledge`, so Telegram should not show the sender a second tick.
- `stealth_presence=true` is the default. The panel keeps chat viewing passive: it does not send Telegram read acknowledgements and it no longer calls `account.updateStatus(offline=True)` after every read/sync.
- `stealth_offline_refresh_seconds=0` is the default. Keep it at `0`; repeatedly calling `account.updateStatus(offline=True)` can itself refresh Last seen to "now". Set a positive value only if you deliberately want periodic offline pings.
- `stealth_disable_live_updates=false` is the default to preserve existing live event-handler features. If Last seen still changes on your account, set it to `true`; new messages will still appear through `/dialogs/sync` and `/messages/sync` polling, but live `events.NewMessage` handlers are paused.
- `POST /messages/{user_id}/read` is local-only.
- `POST /messages/{user_id}/telegram-read` is the explicit opt-in endpoint that really marks the chat as read in Telegram.

Useful endpoints:

- `GET /dialogs`
- `POST /dialogs/sync`
- `GET /messages/{user_id}`
- `POST /messages/{user_id}/sync`
- `POST /messages/{user_id}/read` local-only read
- `POST /messages/{user_id}/telegram-read` real Telegram read acknowledgement
- `GET /messages/{user_id}/{message_id}/media` explicit media download
- `GET /storage/stats`

### Outgoing messages and Online status

`stealth_send_background=true` sends outgoing text/photo/audio with Telethon's `background` flag where supported. This can reduce foreground presence exposure, but Telegram ultimately controls whether a user-account action briefly appears online.

If Telegram still keeps the account online for too long after sending, set:

```txt
stealth_disconnect_after_send=true
```

This disconnects the MTProto session immediately after send/edit/delete. It is stronger, but live updates will stop until the panel reconnects or the backend is restarted.
