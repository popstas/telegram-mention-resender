import asyncio
from types import SimpleNamespace

import pytest

import src.main as main


class DummyClientForList:
    def __init__(self, filters):
        self.connected = False
        self.filters = filters
        self.calls = []

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connected = True
        self.calls.append("connect")

    async def __call__(self, req):
        self.calls.append("request")
        return SimpleNamespace(filters=self.filters)


def create_filter():
    from telethon import types

    return types.DialogFilter(id=1, title=None, pinned_peers=[], include_peers=[], exclude_peers=[])


@pytest.mark.asyncio
async def test_list_folders_connect(monkeypatch):
    f = create_filter()
    client = DummyClientForList([f])
    monkeypatch.setattr(main, "client", client)
    result = await main.list_folders()
    assert client.connected is True
    assert client.calls == ["connect", "request"]
    assert result == [f]


class DummyFolder:
    def __init__(self, title):
        self.title = title
        self.include_peers = []


@pytest.mark.asyncio
async def test_get_folder_with_title_text():
    folders = [DummyFolder(SimpleNamespace(text="MyFolder"))]
    folder = await main.get_folder(folders, "MyFolder")
    assert folder is folders[0]


@pytest.mark.asyncio
async def test_get_folder_not_found():
    folders = [DummyFolder("Other")]
    result = await main.get_folder(folders, "Missing")
    assert result is None


class DummyPeer:
    def __init__(self, cid):
        self.channel_id = cid


class DummyFolderPeers(DummyFolder):
    def __init__(self, title, peers):
        super().__init__(title)
        self.include_peers = [DummyPeer(cid) for cid in peers]


@pytest.mark.asyncio
async def test_get_folders_chat_ids(monkeypatch):
    folders = [DummyFolderPeers("F1", [1, 2])]

    async def fake_list_folders():
        return folders

    monkeypatch.setattr(main, "list_folders", fake_list_folders)

    chat_ids = await main.get_folders_chat_ids(["F1"])
    assert chat_ids == {1, 2}


@pytest.mark.asyncio
async def test_update_instance_chat_ids(monkeypatch):
    async def fake_get_folders_chat_ids(folders):
        assert folders == ["f"]
        return {5}

    async def fake_resolve_entities(entities):
        assert entities == ["e"]
        return {6}

    monkeypatch.setattr(main, "get_folders_chat_ids", fake_get_folders_chat_ids)
    monkeypatch.setattr(main, "resolve_entities", fake_resolve_entities)

    inst = main.Instance(name="i", words=[], target_chat=0, folders=["f"], chat_ids={4}, entities=["e"])

    await main.update_instance_chat_ids(inst, True)
    assert inst.chat_ids == {4, 5, 6}
