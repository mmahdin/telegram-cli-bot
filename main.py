import asyncio

from config import load_config
from music_voice_bot import MusicVoiceBot


async def main() -> None:
    config = load_config()
    bot = MusicVoiceBot(config)
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
