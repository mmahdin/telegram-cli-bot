# Telegram Panel Fixed

This version keeps the Telegram reply/music bot behavior and adds a safer panel storage model.

## Run backend

```bash
cd backend
cp config.example.txt config.txt
# Fill api_id/api_hash/phone
pip install -r requirements.txt
python main.py
```

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

## Important media behavior

The chat UI saves and displays message metadata only. It does not auto-download photos, videos, voices, audios, or documents while loading chats. Every media message appears as a compact file card with a **Download** button. The actual media file is fetched from Telegram only when that button is clicked.

Message/dialog metadata is saved in `backend/panel_data.sqlite3` by default. Temporary media downloads go to `backend/tmp_media_downloads` and are deleted after the download response finishes.


## Read privacy

By default `backend/config.txt` uses `stealth_read=true`. Opening chats in the panel clears only the local JSON badge and does not send Telegram read acknowledgements. This means the sender should not see the second tick just because you viewed the message in this panel.

