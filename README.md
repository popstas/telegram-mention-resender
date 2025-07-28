# telegram-mention-resender

[![Coverage Status](https://coveralls.io/repos/github/popstas/telegram-mention-resender/badge.svg?branch=main)](https://coveralls.io/github/popstas/telegram-mention-resender?branch=main)

This project listens to mentions in specified Telegram chats and forwards
matching messages to a target chat.

# Features

- Listen folders, chats, channels
- Multiple instances for different chats, words and targets
- Each instance has target chat

## Setup

1. Install Python 3.10+ and create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `config-example.yml` to `data/config.yml` and adjust the values:

- `api_id` – your Telegram API ID.
- `api_hash` – your Telegram API hash.
- `session` – path to your session file (default is `data/session`).
- `log_level` – logging level (default is `info`).
- `instances` – list of monitoring instances. Each instance may contain
  `folders`, `chat_ids`, `entities`, `words`, `target_chat`,
  `target_entity` and `folder_mute`.

## Running

```bash
python -m src.main
```

The application will listen to new messages in all configured instances and
forward those containing any of the specified words to their target chats.

## Development

It is built using [Telethon](https://github.com/LonamiWebs/Telethon).

Install pre-commit hooks:

```bash
pre-commit install
```

This will automatically run `black` and `isort` before each commit.
