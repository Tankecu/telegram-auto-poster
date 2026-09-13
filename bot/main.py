"""Entry point: python -m bot  (requires BOT_TOKEN, CHANNEL_ID in .env)"""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from .handlers import router, scheduler_loop

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit(
            "BOT_TOKEN is not set. See .env.example — or run the offline demo:  python demo/run_demo.py"
        )
    channel_id = os.getenv("CHANNEL_ID", "")
    owner_chat = os.getenv("OWNER_CHAT_ID", "")

    bot = Bot(token)
    dp = Dispatcher()
    dp.include_router(router)

    asyncio.create_task(scheduler_loop(bot, channel_id, owner_chat or ""))

    await bot.delete_webhook(drop_pending_updates=True)
    print("Bot is polling; the publishing loop is running. Ctrl+C to stop.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
