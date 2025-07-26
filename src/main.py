import asyncio
import logging
import os
from typing import List

import yaml
from telethon import TelegramClient, events, functions, types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
client = None

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


async def get_folder(folders, folder_name):
    target = None

    for f in folders:
        title = getattr(f, "title", "")
        if hasattr(title, "text"):
            title = title.text
        if title == folder_name:
            target = f
            break

    return target


async def list_folders():
    global client

    if not client or not client.is_connected():
        await client.connect()

    result = await client(functions.messages.GetDialogFiltersRequest())

    folders = []
    for f in result.filters:
        if isinstance(f, types.DialogFilter) or isinstance(
            f, types.DialogFilterChatlist
        ):
            folders.append(f)

    return folders


def get_message_url(message):
    if isinstance(message.peer_id, dict):
        chat_id = (
            message.peer_id.get("channel_id")
            or message.peer_id.get("chat_id")
            or message.peer_id.get("user_id")
        )
    else:
        chat_id = message.peer_id.channel_id
    msg_id = message.id
    url = f"https://t.me/c/{chat_id}/{msg_id}" if chat_id and msg_id else None
    return url


async def get_folders_chat_ids(config_folders):
    chat_ids = set()
    folders = await list_folders()
    for folder_name in config_folders:
        folder = await get_folder(folders, folder_name)
        if folder:
            for dialog in folder.include_peers:
                chat_ids.add(dialog.channel_id)
    return chat_ids


async def main() -> None:
    global client
    config = load_config()
    config_folders = config.get("folders", [])
    words = config.get("words", [])
    target_chat = config.get("target_chat")

    api_id, api_hash, session_name = get_api_credentials(config)

    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    chat_ids = await get_folders_chat_ids(config_folders)
    logger.info(
        "Listening to %d chats from %d folders", len(chat_ids), len(config_folders)
    )

    @client.on(events.NewMessage(chats=list(chat_ids)))
    async def handler(event: events.NewMessage.Event) -> None:
        message = event.message
        if message.raw_text and word_in_text(words, message.raw_text):
            try:
                url = get_message_url(message)
                await client.send_message(target_chat, f"forwarded from: {url}")

                await message.forward_to(target_chat)
                logger.info("Forwarded message %s to %s", message.id, target_chat)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Failed to forward message: %s", exc)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
