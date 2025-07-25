# telegram-mention-resender

This project listens to mentions in specified Telegram chats and forwards
matching messages to a target chat. It is built using [Telethon](https://github.com/LonamiWebs/Telethon).

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
- `folders` – list of folder IDs whose chats should be monitored.
- `words` – list of words to look for.
- `target_chat` – ID of the chat where matched messages will be forwarded.

## Running

```bash
python -m src.main
```

The application will listen to new messages in the configured folders and
forward those containing any of the specified words to the target chat.

## Development

Install pre-commit hooks:

```bash
pre-commit install
```

This will automatically run `black` and `isort` before each commit.
