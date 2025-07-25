import asyncio
import logging
import os
from typing import List

import yaml
from telethon import TelegramClient, events

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


CONFIG_PATH = os.path.join("data", "config.yml")


def load_config() -> dict:
    """Load YAML configuration from CONFIG_PATH."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def get_api_credentials(config: dict) -> tuple:
    """Retrieve Telegram API credentials from configuration."""
    try:
        api_id = int(config["api_id"])
        api_hash = config["api_hash"]
    except KeyError as exc:
        raise RuntimeError("api_id and api_hash must be set in config") from exc
    session = config.get("session", "data/session")
    return api_id, api_hash, session


def word_in_text(words: List[str], text: str) -> bool:
    """Return True if any of the words is found in text."""
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in words)


async def main() -> None:
    config = load_config()
    folders = config.get("folders", [])
    words = config.get("words", [])
    target_chat = config.get("target_chat")

    api_id, api_hash, session_name = get_api_credentials(config)

    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    chat_ids = set()
    for folder in folders:
        async for dialog in client.iter_dialogs(folder=folder):
            chat_ids.add(dialog.id)

    logger.info("Listening to %d chats", len(chat_ids))

    @client.on(events.NewMessage(chats=list(chat_ids)))
    async def handler(event: events.NewMessage.Event) -> None:
        message = event.message
        if message.raw_text and word_in_text(words, message.raw_text):
            try:
                await message.forward_to(target_chat)
                logger.info("Forwarded message %s to %s", message.id, target_chat)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Failed to forward message: %s", exc)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
