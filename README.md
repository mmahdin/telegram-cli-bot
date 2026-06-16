# Telegram Music Voice Bot

این نسخه فقط یک کار انجام می‌دهد: وقتی با اکانت خودتان روی پیام کسی ریپلای می‌کنید و دستور با `آهنگ` شروع می‌شود، آهنگ مشخص‌شده را از چت/کانال منبع دانلود می‌کند، بازه‌ی زمانی خواسته‌شده را crop می‌کند و به‌صورت voice روی همان پیام می‌فرستد.

## فایل‌ها

- `main.py`: نقطه‌ی شروع برنامه
- `config.py`: خواندن تنظیمات از `config.txt`
- `music_voice_bot.py`: منطق تشخیص دستور، دانلود آهنگ، برش با FFmpeg و ارسال voice
- `requirements.txt`: وابستگی‌های پایتون
- `config.example.txt`: نمونه تنظیمات

## راه‌اندازی

```bash
pip install -r requirements.txt
```

FFmpeg هم باید روی سیستم نصب باشد:

```bash
# Termux
pkg install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

بعد فایل تنظیمات را بسازید:

```bash
cp config.example.txt config.txt
```

داخل `config.txt` مقدارهای `api_id` و `api_hash` را قرار دهید.

## اجرای ربات

```bash
python main.py
```

نام session در کد دقیقاً `session` است؛ بنابراین Telethon فایل `session.session` را می‌سازد/استفاده می‌کند. اگر `session.session` از قبل کنار `main.py` وجود داشته باشد، دوباره لاگین نمی‌خواهد.

آهنگ‌های دانلودشده داخل cache با این الگو ذخیره می‌شوند و در اجراهای بعدی دوباره دانلود نمی‌شوند:

```text
downloaded_audios/cache/audio_<message_id>.mp3
# example:
downloaded_audios/cache/audio_4447.mp3
```

## دستور

روی پیام شخص مورد نظر ریپلای کنید و بنویسید:

```text
آهنگ 4191 1:09 1:17
```

معنی دستور بالا:

- پیام شماره `4191` از `source_chat` خوانده می‌شود.
- بازه‌ی `1:09` تا `1:17` برش می‌خورد.
- خروجی به‌صورت voice روی پیام ریپلای‌شده ارسال می‌شود.

فرمت زمان می‌تواند `M:SS` یا `H:MM:SS` باشد.
