import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import List, Set

import yaml
from telethon import TelegramClient, events, functions, types
from telethon.utils import get_peer_id


def setup_logging(level: str = "info") -> None:
    """Configure logging for the application."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(levelname)s - %(message)s")
    logging.getLogger("telethon").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)
client = None


@dataclass
class Instance:
    """Configuration for a single monitoring instance."""

    name: str
    words: List[str]
    target_chat: int
    folders: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    chat_ids: Set[int] = field(default_factory=set)


instances: List[Instance] = []

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
    if not config_folders:
        return chat_ids
    folders = await list_folders()
    for folder_name in config_folders:
        folder = await get_folder(folders, folder_name)
        if folder:
            for dialog in folder.include_peers:
                chat_ids.add(dialog.channel_id)
    return chat_ids


async def resolve_entities(entities: List[str]) -> Set[int]:
    """Resolve Telegram links or usernames to chat IDs."""
    resolved = set()
    for ent in entities:
        try:
            entity = await client.get_entity(ent)
            resolved.add(get_peer_id(entity))
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to resolve entity %s: %s", ent, exc)
    return resolved


async def update_instance_chat_ids(instance: Instance, first_run: bool = False) -> None:
    """Refresh chat IDs for a single instance."""
    new_ids = await get_folders_chat_ids(instance.folders)
    new_ids.update(instance.chat_ids)
    new_ids.update(await resolve_entities(instance.entities))
    instance.chat_ids = new_ids
    log_level = logging.INFO if first_run else logging.DEBUG
    logger.log(
        log_level,
        "Instance '%s': listening to %d chats from %d folders and %d entities",
        instance.name,
        len(instance.chat_ids),
        len(instance.folders),
        len(instance.entities),
    )


async def rescan_loop(instance: Instance, interval: int = 3600) -> None:
    """Periodically rescan folders for chat IDs."""
    while True:
        await asyncio.sleep(interval)
        await update_instance_chat_ids(instance, False)


async def load_instances(config: dict) -> List[Instance]:
    """Parse instance configurations from config."""
    if "instances" not in config:
        config = {
            "instances": [
                {
                    "name": "default",
                    "folders": config.get("folders", []),
                    "chat_ids": config.get("chat_ids", []),
                    "entities": config.get("entities", []),
                    "words": config.get("words", []),
                    "target_chat": config.get("target_chat"),
                }
            ]
        }

    parsed_instances: List[Instance] = []
    for inst_cfg in config.get("instances", []):
        instance = Instance(
            name=inst_cfg.get("name", "instance"),
            folders=inst_cfg.get("folders", []),
            chat_ids=set(inst_cfg.get("chat_ids", [])),
            entities=inst_cfg.get("entities", []),
            words=inst_cfg.get("words", []),
            target_chat=inst_cfg.get("target_chat"),
        )
        parsed_instances.append(instance)
    return parsed_instances


async def main() -> None:
    global client, instances
    config = load_config()

    setup_logging(config.get("log_level", "info"))

    api_id, api_hash, session_name = get_api_credentials(config)

    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    instances = await load_instances(config)
    for inst in instances:
        await update_instance_chat_ids(inst, True)
        asyncio.create_task(rescan_loop(inst))

    @client.on(events.NewMessage)
    async def handler(event: events.NewMessage.Event) -> None:
        message = event.message
        for inst in instances:
            if event.chat_id not in inst.chat_ids:
                continue
            if message.raw_text and word_in_text(inst.words, message.raw_text):
                try:
                    url = get_message_url(message)
                    await client.send_message(
                        inst.target_chat, f"forwarded from: {url}"
                    )
                    await message.forward_to(inst.target_chat)
                    logger.info(
                        "Forwarded message %s to %s for %s",
                        message.id,
                        inst.target_chat,
                        inst.name,
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    logger.error("Failed to forward message: %s", exc)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
