# Telegram AutoPoster Bot

Automatic bot for scheduling and posting messages to Telegram channels.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file based on `.env` and fill it with your data:
- `API_ID` and `API_HASH` - get them from https://my.telegram.org
- `BOT_TOKEN` - get it from @BotFather in Telegram
- `CHANNEL_ID` - your Telegram channel ID

3. Run the bot:
```bash
python bot.py
```

## Usage

1. Find the bot in Telegram
2. Send `/start` to begin
3. Send any message - the bot will automatically schedule it for posting in the channel

## Features

- Automatic message scheduling
- SQLite database storage
- Action logging
- Message checking and posting every minute
- Error handling and retry attempts
