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

Read privacy:

- `stealth_read=true` is the default. Opening a chat in the panel only clears the local JSON unread badge. It does **not** call Telethon `send_read_acknowledge`, so Telegram should not show the sender a second tick.
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
