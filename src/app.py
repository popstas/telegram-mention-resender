import asyncio
import logging
from typing import List

from telethon import TelegramClient, events, types

from . import langfuse_utils, prompts, telegram_utils
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

langfuse = None

# Use shared stats tracker
stats = global_stats

NEGATIVE_REACTIONS = {"👎"}  # thumbs down
POSITIVE_REACTIONS = {"👍"}  # thumbs up

# Track messages already forwarded for reactions
forwarded_positive: set[tuple[int, int]] = set()
forwarded_negative: set[tuple[int, int]] = set()


def setup_logging(level: str = "info") -> None:
    """Configure logging for the application."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(levelname)s - %(message)s")
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("langfuse").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
    logging.getLogger("httpcore.connection").setLevel(logging.WARNING)


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
    if message.raw_text and word_in_text(inst.negative_words, message.raw_text):
        logger.debug(
            "Ignoring message %s for %s due to negative_words",
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
    used_quote: str | None = None
    used_reasoning: str | None = None

    if message.raw_text:
        w = find_word(inst.words, message.raw_text)
        if w:
            forward = True
            used_word = w
        else:
            for p in inst.prompts:
                res = await match_prompt(p, message.raw_text, inst.name, chat_name)
                sc = res.score
                if sc > used_score:
                    used_score = sc
                    used_prompt = p
                    used_quote = res.quote
                    used_reasoning = res.reasoning
                if sc >= (p.threshold or 4):
                    forward = True
                    break
    if forward:
        try:
            if not inst.no_forward_message:
                text = await get_forward_message_text(
                    message,
                    prompt=used_prompt,
                    score=used_score,
                    word=used_word,
                    quote=used_quote,
                    reasoning=used_reasoning,
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
                if not inst.no_forward_message:
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


async def handle_reaction(update: "types.UpdateMessageReactions") -> None:
    """Forward reacted messages to true/false positive entities."""

    if not update or not hasattr(update, "reactions"):
        return

    emojis: list[str] = []
    for rc in getattr(update.reactions, "results", []):
        reaction = getattr(rc, "reaction", None)
        if isinstance(reaction, types.ReactionEmoji):
            emojis.append(reaction.emoticon)

    positive = any(e in POSITIVE_REACTIONS for e in emojis)
    negative = any(e in NEGATIVE_REACTIONS for e in emojis)
    if not (positive or negative):
        return

    peer_id = await telegram_utils.to_event_chat_id(update.peer)
    key = (peer_id, update.msg_id)

    if positive and key in forwarded_positive:
        logger.debug("Skip message %s already forwarded as positive", key)
        return
    if negative and key in forwarded_negative:
        logger.debug("Skip message %s already forwarded as negative", key)
        return

    for inst in instances:
        if not inst.target_entity:
            continue
        entity = await telegram_utils.get_entity(inst.target_entity)
        target_id = await telegram_utils.to_event_chat_id(entity)
        if peer_id != target_id:
            continue

        dest = None
        if positive:
            dest = inst.true_positive_entity
        elif negative:
            dest = inst.false_positive_entity
        if not dest:
            continue

        message = await client.get_messages(update.peer, ids=update.msg_id)
        if not message:
            return
        forwarded = await message.forward_to(dest)
        if positive:
            forwarded_positive.add(key)
        elif negative:
            forwarded_negative.add(key)
        f_url = get_message_url(forwarded) if forwarded else None
        logger.info(
            "Forwarded message %s from %s to %s for %s (target url: %s)",
            message.id,
            inst.target_entity,
            dest,
            inst.name,
            f_url,
        )
        break


async def main() -> None:
    global client, instances, config
    config = load_config()
    prompts.config.update(config)
    global langfuse
    langfuse = langfuse_utils.init_langfuse(config)
    prompts.langfuse = langfuse

    setup_logging(config.get("log_level", "info"))

    api_id, api_hash, session_name = get_api_credentials(config)

    client = TelegramClient(session_name, api_id, api_hash)
    telegram_utils.client = client
    await client.start()

    prompts.stats = stats

    instances = await load_instances(config)
    await prompts.load_langfuse_prompts(instances)
    for inst in instances:
        await update_instance_chat_ids(inst, True)
        asyncio.create_task(rescan_loop(inst))

    @client.on(events.Raw(types.UpdateMessageReactions))
    async def reaction_event_handler(update) -> None:
        await handle_reaction(update)

    @client.on(events.NewMessage)
    async def handler(event: events.NewMessage.Event) -> None:
        username = getattr(getattr(event.message, "sender", None), "username", None)
        user_id = getattr(getattr(event.message, "sender", None), "id", None)
        if user_id and user_id in config.get("ignore_user_ids", []):
            logger.debug("Ignoring message from id %s", user_id)
            return
        if username and username.lower() in [
            u.lower() for u in config.get("ignore_usernames", [])
        ]:
            logger.debug("Ignoring message from @%s", username)
            return

        for inst in instances:
            if event.chat_id in inst.chat_ids:
                await process_message(inst, event)

    await client.run_until_disconnected()
