import asyncio
import atexit
import datetime
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import List, Set

import yaml
from telethon import TelegramClient, events, functions, types
from telethon.utils import get_peer_id, resolve_id


def setup_logging(level: str = "info") -> None:
    """Configure logging for the application."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(levelname)s - %(message)s")
    logging.getLogger("telethon").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)
client = None
config: dict = {}

# Cache for entity names by chat_identifier
entity_name_cache = {}


def get_safe_name(name: str) -> str:
    """Return ``name`` with unsafe characters replaced by underscores."""
    safe = re.sub(r"[^\w\-_.]", "_", name.strip())
    return safe or "chat_history"


@dataclass
class Instance:
    """Configuration for a single monitoring instance."""

    name: str
    words: List[str]
    target_chat: int | None = None
    target_entity: str | None = None
    folders: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    chat_ids: Set[int] = field(default_factory=set)
    folder_mute: bool = False
    prompts: List[str] = field(default_factory=list)
    prompt_threshold: int = 4


instances: List[Instance] = []

MUTE_FOREVER = 2**31 - 1

CONFIG_PATH = os.path.join("data", "config.yml")
STATS_PATH = os.path.join("data", "stats.json")


class StatsTracker:
    """Collect and periodically flush statistics about processed messages."""

    def __init__(self, path: str, flush_interval: int = 60) -> None:
        self.path = path
        self.flush_interval = flush_interval
        self.last_flush = time.monotonic()
        self.dirty = False
        self.data = {"total": 0, "instances": []}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:  # pragma: no cover - corrupt file
                self.data = {"total": 0, "instances": []}

    def _get_inst(self, name: str) -> dict:
        for inst in self.data.get("instances", []):
            if inst.get("name") == name:
                return inst
        inst = {"name": name, "total": 0, "days": {}}
        self.data.setdefault("instances", []).append(inst)
        return inst

    def increment(self, name: str) -> None:
        inst = self._get_inst(name)
        self.data["total"] = self.data.get("total", 0) + 1
        inst["total"] = inst.get("total", 0) + 1
        day = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
        inst["days"][day] = inst["days"].get(day, 0) + 1
        self.dirty = True
        if time.monotonic() - self.last_flush >= self.flush_interval:
            self.flush()

    def flush(self) -> None:
        if not self.dirty:
            return
        logger.debug("Flushing stats to %s", self.path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)
        self.last_flush = time.monotonic()
        self.dirty = False


stats = StatsTracker(STATS_PATH)
atexit.register(stats.flush)


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


async def match_prompts(prompts: List[str], text: str, threshold: int) -> int:
    """Return similarity score from 0 to 5 for ``text`` using OpenAI."""
    if not prompts or not config.get("openai_api_key"):
        return 0

    from openai import OpenAI
    from pydantic import BaseModel

    class EvaluateResult(BaseModel):
        similarity: int

    client = OpenAI(api_key=config["openai_api_key"])
    model = config.get("openai_model", "gpt-4.1-mini")

    best = 0
    for prompt in prompts:
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "return only number of similarity: 0 - not match at all, 5 - strongly match. "
                    f"Message: {text}"
                ),
            },
        ]
        try:
            completion = await asyncio.to_thread(
                client.chat.completions.parse,
                model=model,
                messages=messages,
                response_model=EvaluateResult,
            )
            similarity = completion.choices[0].message.parsed.similarity
        except Exception as exc:  # pragma: no cover - external call
            logger.error("Failed to query OpenAI: %s", exc)
            similarity = 0
        logger.debug("Prompt check: %s -> %s", prompt, similarity)
        best = max(best, similarity)
        if similarity >= threshold:
            return similarity

    return best


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
    """Return a t.me URL if the message has ``channel_id``."""
    chat_id = getattr(message.peer_id, "channel_id", None)
    msg_id = message.id
    url = f"https://t.me/c/{chat_id}/{msg_id}" if chat_id and msg_id else None
    return url


async def get_message_source(message):
    """Return message source with chat type, name, and optional URL."""
    url = get_message_url(message)
    peer = message.peer_id

    if isinstance(peer, types.PeerChannel):
        chat_type = "channel"
    elif isinstance(peer, types.PeerChat):
        chat_type = "group"
    else:
        chat_type = "private"

    name = await get_chat_name(peer)

    if chat_type == "private":
        username = getattr(getattr(message, "sender", None), "username", None)
        if username:
            name = f"@{username}"
    else:
        chat_username = getattr(getattr(message, "chat", None), "username", None)
        if chat_username:
            name = f"@{chat_username}"

    if chat_type == "private":
        result = f"Forwarded from: {chat_type} {name}"
    else:
        result = f"Forwarded from: {name}"
    if url:
        result += f" - {url}"
    return result


async def to_event_chat_id(peer) -> int | None:
    """Convert various peer representations to ``event.chat_id`` format."""
    if peer is None:
        return None

    if isinstance(peer, int):
        if peer <= 0:
            return peer
        try:
            ent = await client.get_input_entity(peer)
            return get_peer_id(ent)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to resolve peer %s: %s", peer, exc)
            return -peer

    try:
        return get_peer_id(peer)
    except Exception:
        if hasattr(peer, "channel_id"):
            return get_peer_id(types.PeerChannel(peer.channel_id))
        if hasattr(peer, "chat_id"):
            return get_peer_id(types.PeerChat(peer.chat_id))
        if hasattr(peer, "user_id"):
            return peer.user_id
    return None


async def normalize_chat_ids(ids: Set[int]) -> Set[int]:
    """Normalize a set of chat IDs to ``event.chat_id`` format."""
    result = set()
    for cid in ids:
        result.add(await to_event_chat_id(cid))
    return {i for i in result if i is not None}


async def get_folders_chat_ids(config_folders):
    """Return chat IDs for all peers included in the given folders."""
    chat_ids = set()
    if not config_folders:
        return chat_ids

    folders = await list_folders()
    for folder_name in config_folders:
        folder = await get_folder(folders, folder_name)
        if not folder:
            continue

        for dialog in folder.include_peers:
            chat_id = await to_event_chat_id(dialog)
            if chat_id is not None:
                chat_ids.add(chat_id)

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


async def mute_notify_peer(notify_peer) -> None:
    try:
        settings = await client(functions.account.GetNotifySettingsRequest(notify_peer))
        mute_until = getattr(settings, "mute_until", None)
        ts = (
            int(mute_until.timestamp())
            if hasattr(mute_until, "timestamp")
            else (mute_until or 0)
        )
        if ts != MUTE_FOREVER:
            await client(
                functions.account.UpdateNotifySettingsRequest(
                    peer=notify_peer,
                    settings=types.InputPeerNotifySettings(mute_until=MUTE_FOREVER),
                )
            )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to mute peer %s: %s", notify_peer, exc)


async def mute_peer_and_topics(peer) -> None:
    logger.debug("Muting peer %s - %s", peer, await get_entity_name(peer.channel_id))
    try:
        ip = await client.get_input_entity(peer)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to resolve peer %s for mute: %s", peer, exc)
        return

    await mute_notify_peer(types.InputNotifyPeer(ip))

    # try:
    #     topics = await client(
    #         functions.channels.GetForumTopicsRequest(
    #             channel=ip,
    #             offset_date=None,
    #             offset_id=0,
    #             offset_topic=0,
    #             limit=100,
    #         )
    #     )
    #     for t in getattr(topics, "topics", []):
    #         notify = types.InputNotifyForumTopic(peer=ip, top_msg_id=t.top_message)
    #         await mute_notify_peer(notify)
    # except Exception:
    #     pass


async def mute_chats_from_folders(folder_names: List[str]) -> None:
    if not folder_names:
        return
    folders = await list_folders()
    for fname in folder_names:
        folder = await get_folder(folders, fname)
        if not folder:
            continue
        for p in getattr(folder, "include_peers", []):
            await mute_peer_and_topics(p)


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
                    "target_entity": config.get("target_entity"),
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
            target_entity=inst_cfg.get("target_entity"),
            folder_mute=inst_cfg.get("folder_mute", False),
            prompts=inst_cfg.get("prompts", []),
            prompt_threshold=inst_cfg.get("prompt_threshold", 4),
        )
        parsed_instances.append(instance)
    return parsed_instances


async def get_chat_name(chat_identifier: str, safe: bool = False) -> str:
    if not chat_identifier:
        return "chat_history"

    # Check cache first (safe names only for hashable identifiers)
    if (
        safe
        and isinstance(chat_identifier, (int, str))
        and chat_identifier in entity_name_cache
    ):
        return entity_name_cache[chat_identifier]

    try:
        entity = await client.get_entity(chat_identifier)
        if not entity:
            return None

        if hasattr(entity, "title"):
            name = entity.title
        elif hasattr(entity, "username") and entity.username:
            name = entity.username
        elif hasattr(entity, "first_name") or hasattr(entity, "last_name"):
            name = " ".join(
                filter(
                    None,
                    [
                        getattr(entity, "first_name", ""),
                        getattr(entity, "last_name", ""),
                    ],
                )
            )
        else:
            name = str(entity.id)

        safe_name = get_safe_name(name)

        if safe:
            if isinstance(chat_identifier, (int, str)):
                entity_name_cache[chat_identifier] = safe_name
            return safe_name

        return name.strip() or "chat_history"

    except Exception:
        chat = str(chat_identifier)
        if chat.startswith("@"):
            chat = chat[1:]
        elif "//" in chat:
            chat = chat.split("?")[0].rstrip("/").split("/")[-1]
            if chat.startswith("+"):
                chat = "invite_" + chat[1:]

        safe_name = get_safe_name(chat)
        if safe:
            if isinstance(chat_identifier, (int, str)):
                entity_name_cache[chat_identifier] = safe_name
            return safe_name
        return chat or "chat_history"


async def get_entity_name(peer_id, safe: bool = False) -> str:
    """Return name for the given ``peer_id``."""
    if isinstance(peer_id, int):
        pid, cls = resolve_id(peer_id)
        if cls == types.PeerChannel:
            peer = types.PeerChannel(pid)
        elif cls == types.PeerChat:
            peer = types.PeerChat(pid)
        else:
            peer = types.PeerUser(pid)
    else:
        peer = peer_id

    return await get_chat_name(peer, safe=safe)


async def process_message(inst: Instance, event: events.NewMessage.Event) -> None:
    """Handle a new message for a specific instance."""
    stats.increment(inst.name)
    message = event.message
    chat_name = await get_chat_name(event.chat_id, safe=True)
    forward = False
    if message.raw_text:
        if word_in_text(inst.words, message.raw_text):
            forward = True
        elif inst.prompts:
            score = await match_prompts(
                inst.prompts, message.raw_text, inst.prompt_threshold
            )
            logger.debug("Prompt score %s for %s", score, inst.name)
            if score >= inst.prompt_threshold:
                forward = True
    if forward:
        try:
            source = await get_message_source(message)
            destinations = []
            dest_names = []
            if inst.target_chat is not None:
                destinations.append(inst.target_chat)
                dest_names.append(await get_chat_name(inst.target_chat, safe=True))
            if inst.target_entity:
                destinations.append(inst.target_entity)
                dest_names.append(await get_chat_name(inst.target_entity, safe=True))
            for dest, dname in zip(destinations, dest_names):
                await client.send_message(dest, source)
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
        for inst in instances:
            if event.chat_id in inst.chat_ids:
                await process_message(inst, event)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
