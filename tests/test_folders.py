import asyncio
from types import SimpleNamespace

import pytest

import src.app as app
import src.config as config
import src.telegram_utils as tgu


@pytest.mark.asyncio
async def test_list_folders_connect(monkeypatch, create_filter, dummy_client_for_list):
    f = create_filter()
    client = dummy_client_for_list([f])
    monkeypatch.setattr(tgu, "client", client)
    result = await tgu.list_folders()
    assert client.connected is True
    assert client.calls == ["connect", "request"]
    assert result == [f]


@pytest.mark.asyncio
async def test_get_folder_with_title_text(dummy_folder_cls):
    folders = [dummy_folder_cls(SimpleNamespace(text="MyFolder"))]
    folder = await tgu.get_folder(folders, "MyFolder")
    assert folder is folders[0]


@pytest.mark.asyncio
async def test_get_folder_not_found(dummy_folder_cls):
    folders = [dummy_folder_cls("Other")]
    result = await tgu.get_folder(folders, "Missing")
    assert result is None


@pytest.mark.asyncio
async def test_get_folders_chat_ids(monkeypatch, dummy_folder_peers_cls):
    folders = [dummy_folder_peers_cls("F1", [1, 2])]

    async def fake_list_folders():
        return folders

    monkeypatch.setattr(tgu, "list_folders", fake_list_folders)

    from telethon import types

    chat_ids = await tgu.get_folders_chat_ids(["F1"])
    expected = {
        tgu.get_peer_id(types.PeerChannel(1)),
        tgu.get_peer_id(types.PeerChannel(2)),
    }
    assert chat_ids == expected


@pytest.mark.asyncio
async def test_update_instance_chat_ids(monkeypatch):
    async def fake_get_folders_chat_ids(folders):
        assert folders == ["f"]
        return {5}

    async def fake_resolve_entities(entities):
        assert entities == ["e"]
        return {6}

    added_topics: list[tuple[list[str], list]] = []

    async def fake_add_topics(folders, topics):
        added_topics.append((folders, topics))
        return []

    async def fake_get_input_entity(cid):
        from telethon import types

        return types.InputPeerChat(cid)

    client = SimpleNamespace(get_input_entity=fake_get_input_entity)

    monkeypatch.setattr(tgu, "client", client)
    monkeypatch.setattr(app, "get_folders_chat_ids", fake_get_folders_chat_ids)
    monkeypatch.setattr(app, "resolve_entities", fake_resolve_entities)
    monkeypatch.setattr(app, "add_topic_from_folders", fake_add_topics)

    inst = app.Instance(
        name="i",
        words=[],
        target_chat=0,
        folders=["f"],
        chat_ids={4},
        entities=["e"],
        folder_add_topic=[config.FolderTopic(name="Topic")],
    )

    await app.update_instance_chat_ids(inst, True)
    assert inst.chat_ids == {-4, -5, -6}
    assert added_topics == [(["f"], inst.folder_add_topic)]


@pytest.mark.asyncio
async def test_update_instance_chat_ids_mute(monkeypatch):
    async def fake_get_folders_chat_ids(folders):
        return set()

    async def fake_resolve_entities(entities):
        return set()

    called = []

    async def fake_mute(names):
        called.append(names)

    monkeypatch.setattr(tgu, "client", SimpleNamespace())
    monkeypatch.setattr(app, "get_folders_chat_ids", fake_get_folders_chat_ids)
    monkeypatch.setattr(app, "resolve_entities", fake_resolve_entities)
    monkeypatch.setattr(app, "mute_chats_from_folders", fake_mute)

    inst = app.Instance(
        name="i", words=[], target_chat=0, folders=["f"], folder_mute=True
    )
    await app.update_instance_chat_ids(inst, True)
    assert called == [["f"]]


@pytest.mark.asyncio
async def test_get_folders_chat_ids_channel(monkeypatch):
    from telethon import types

    channel = types.InputPeerChannel(1, 2)
    folder = SimpleNamespace(title="F1", include_peers=[channel])

    async def fake_list_folders():
        return [folder]

    monkeypatch.setattr(tgu, "list_folders", fake_list_folders)

    chat_ids = await tgu.get_folders_chat_ids(["F1"])
    expected = {tgu.get_peer_id(types.PeerChannel(1))}
    assert chat_ids == expected


@pytest.mark.asyncio
async def test_get_folders_chat_ids_chat_and_user(monkeypatch):
    from telethon import types

    chat = types.InputPeerChat(7)
    user = types.InputPeerUser(8, 1)
    folder = SimpleNamespace(title="F2", include_peers=[chat, user])

    async def fake_list_folders():
        return [folder]

    monkeypatch.setattr(tgu, "list_folders", fake_list_folders)

    chat_ids = await tgu.get_folders_chat_ids(["F2"])
    expected = {
        tgu.get_peer_id(types.PeerChat(7)),
        tgu.get_peer_id(types.PeerUser(8)),
    }
    assert chat_ids == expected


@pytest.mark.asyncio
async def test_add_topic_from_folders(monkeypatch, caplog):
    from datetime import datetime

    from telethon import functions, types

    caplog.set_level("INFO")

    class DummyClient:
        def __init__(self):
            self.topics: list = []
            self.sent: list = []

        async def get_entity(self, _):
            return types.Channel(
                id=123,
                title="Chat",
                photo=None,
                date=datetime.now(),
                megagroup=True,
                forum=True,
            )

        async def __call__(self, request):
            if isinstance(request, functions.channels.GetForumTopicsRequest):
                matches = [t for t in self.topics if t.title == request.q]
                return SimpleNamespace(topics=matches)
            if isinstance(request, functions.channels.CreateForumTopicRequest):
                topic_id = len(self.topics) + 1
                topic = SimpleNamespace(id=topic_id, title=request.title)
                self.topics.append(topic)
                return SimpleNamespace()
            raise AssertionError("Unexpected request")

        async def send_message(self, entity, message, **kwargs):
            self.sent.append((entity, message, kwargs))

    dummy_client = DummyClient()
    monkeypatch.setattr(tgu, "client", dummy_client)

    folder = SimpleNamespace(title="Folder", include_peers=[SimpleNamespace(id=1)])

    async def fake_list_folders():
        return [folder]

    monkeypatch.setattr(tgu, "list_folders", fake_list_folders)

    topics = [config.FolderTopic(name="Topic", message="hello")]
    result = await tgu.add_topic_from_folders(["Folder"], topics)

    assert result == [(123, 1, "Chat")]
    assert dummy_client.sent
    _, sent_message, kwargs = dummy_client.sent[0]
    assert sent_message == "hello"
    assert isinstance(kwargs.get("reply_to"), types.InputReplyToMessage)
    assert kwargs["reply_to"].top_msg_id == 1
    assert kwargs["reply_to"].reply_to_msg_id == 1
    assert any("chat 123 thread 1" in rec.message for rec in caplog.records)
