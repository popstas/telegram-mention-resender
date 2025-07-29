import asyncio
import logging
from typing import List

from telethon import TelegramClient, events

from . import prompts, telegram_utils
from .config import Instance, get_api_credentials, load_config, load_instances
from .prompts import Prompt, match_prompt
from .stats import stats as global_stats
from .telegram_utils import (
    find_word,
    get_chat_name,
    get_folders_chat_ids,
    get_forward_message_text,
    get_message_url,
    mute_chats_from_folders,
    normalize_chat_ids,
    resolve_entities,
    word_in_text,
)

logger = logging.getLogger(__name__)

client: TelegramClient | None = None
config: dict = {}
instances: List[Instance] = []

# Use shared stats tracker
stats = global_stats


def setup_logging(level: str = "info") -> None:
    """Configure logging for the application."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(levelname)s - %(message)s")
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


async def update_instance_chat_ids(instance: Instance, first_run: bool = False) -> None:
    """Refresh chat IDs for a single instance."""
    new_ids = await get_folders_chat_ids(instance.folders)
    new_ids.update(instance.chat_ids)
    new_ids.update(await resolve_entities(instance.entities))
    instance.chat_ids = await normalize_chat_ids(new_ids)
    if instance.folder_mute:
        await mute_chats_from_folders(instance.folders)
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
    global config
    while True:
        await asyncio.sleep(interval)
        config = load_config()
        prompts.config.update(config)
        await update_instance_chat_ids(instance, False)


async def process_message(inst: Instance, event: events.NewMessage.Event) -> None:
    """Handle a new message for a specific instance."""
    message = event.message
    if message.raw_text and word_in_text(inst.ignore_words, message.raw_text):
        logger.debug(
            "Ignoring message %s for %s due to ignore_words",
            message.id,
            inst.name,
        )
        return
    stats.increment(inst.name)
    chat_name = await get_chat_name(event.chat_id, safe=True)
    forward = False
    used_word: str | None = None
    used_prompt: Prompt | None = None
    used_score = 0
    used_fragment: str | None = None

    if message.raw_text:
        w = find_word(inst.words, message.raw_text)
        if w:
            forward = True
            used_word = w
        else:
            for p in inst.prompts:
                res = await match_prompt(p, message.raw_text, inst.name)
                sc = res.similarity
                if sc > used_score:
                    used_score = sc
                    used_prompt = p
                    used_fragment = res.main_fragment
                if sc >= (p.threshold or 4):
                    forward = True
                    break
    if forward:
        try:
            text = await get_forward_message_text(
                message,
                prompt=used_prompt,
                score=used_score,
                word=used_word,
                fragment=used_fragment,
            )
            destinations = []
            dest_names = []
            if inst.target_chat is not None:
                destinations.append(inst.target_chat)
                dest_names.append(await get_chat_name(inst.target_chat, safe=True))
            if inst.target_entity:
                destinations.append(inst.target_entity)
                dest_names.append(await get_chat_name(inst.target_entity, safe=True))
            for dest, dname in zip(destinations, dest_names):
                await client.send_message(dest, text)
                forwarded = await message.forward_to(dest)
                f_url = get_message_url(forwarded) if forwarded else None
                logger.info(
                    "Forwarded message %s from %s to %s for %s (target url: %s)",
                    message.id,
                    chat_name,
                    dname,
                    inst.name,
                    f_url,
                )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to forward message: %s", exc)
    else:
        logger.debug(
            "Message %s from %s not forwarded for %s",
            message.id,
            chat_name,
            inst.name,
        )


async def main() -> None:
    global client, instances, config
    config = load_config()
    prompts.config.update(config)

    setup_logging(config.get("log_level", "info"))

    api_id, api_hash, session_name = get_api_credentials(config)

    client = TelegramClient(session_name, api_id, api_hash)
    telegram_utils.client = client
    await client.start()

    prompts.stats = stats

    instances = await load_instances(config)
    for inst in instances:
        await update_instance_chat_ids(inst, True)
        asyncio.create_task(rescan_loop(inst))

    @client.on(events.NewMessage)
    async def handler(event: events.NewMessage.Event) -> None:
        username = getattr(getattr(event.message, "sender", None), "username", None)
        if username and username.lower() in [
            u.lower() for u in config.get("ignore_usernames", [])
        ]:
            logger.debug("Ignoring message from @%s", username)
            return

        for inst in instances:
            if event.chat_id in inst.chat_ids:
                await process_message(inst, event)

    await client.run_until_disconnected()
