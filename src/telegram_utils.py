import asyncio
import logging
import re
from typing import List, Set

from telethon import functions, types
from telethon.utils import get_peer_id, resolve_id

logger = logging.getLogger(__name__)

client = None
entity_name_cache: dict = {}

MUTE_FOREVER = 2**31 - 1


def get_safe_name(name: str) -> str:
    """Return ``name`` with unsafe characters replaced by underscores."""
    safe = re.sub(r"[^\w\-_.]", "_", name.strip())
    return safe or "chat_history"


def word_in_text(words: List[str], text: str) -> bool:
    """Return True if any of the words is found in text."""
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in words)


def find_word(words: List[str], text: str) -> str | None:
    """Return the first matching word found in text."""
    text_lower = text.lower()
    for word in words:
        if word.lower() in text_lower:
            return word
    return None


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
        base_name = f"{chat_type} {name}"
    else:
        base_name = name

    if url and chat_type != "private":
        result = f"Forwarded from: [{base_name}]({url})"
    else:
        result = f"Forwarded from: {base_name}"
        if url:
            result += f" - {url}"
    return result


def get_forward_reason_text(
    *,
    prompt=None,
    score: int | None = None,
    word: str | None = None,
    fragment: str | None = None,
) -> str:
    """Return human-readable reason for forwarding a message."""
    if word:
        return f"word: {word}"
    if prompt is not None and score is not None:
        name = getattr(prompt, "name", None) or "prompt"
        reason = f"{name}: {score}/5"
        if fragment:
            reason += f" - `{fragment}`"
        return reason
    return ""


async def get_forward_message_text(
    message,
    *,
    prompt=None,
    score: int | None = None,
    word: str | None = None,
    fragment: str | None = None,
) -> str:
    """Return text to send before forwarding ``message``."""
    reason = get_forward_reason_text(
        prompt=prompt, score=score, word=word, fragment=fragment
    )
    source = await get_message_source(message)
    if reason:
        return f"{reason}\n\n{source}"
    return source


async def get_chat_name(chat_identifier: str, safe: bool = False) -> str:
    if not chat_identifier:
        return "chat_history"

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
