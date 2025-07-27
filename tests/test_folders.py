import asyncio
from types import SimpleNamespace

import pytest

import src.main as main


@pytest.mark.asyncio
async def test_list_folders_connect(monkeypatch, create_filter, dummy_client_for_list):
    f = create_filter()
    client = dummy_client_for_list([f])
    monkeypatch.setattr(main, "client", client)
    result = await main.list_folders()
    assert client.connected is True
    assert client.calls == ["connect", "request"]
    assert result == [f]


@pytest.mark.asyncio
async def test_get_folder_with_title_text(dummy_folder_cls):
    folders = [dummy_folder_cls(SimpleNamespace(text="MyFolder"))]
    folder = await main.get_folder(folders, "MyFolder")
    assert folder is folders[0]


@pytest.mark.asyncio
async def test_get_folder_not_found(dummy_folder_cls):
    folders = [dummy_folder_cls("Other")]
    result = await main.get_folder(folders, "Missing")
    assert result is None


@pytest.mark.asyncio
async def test_get_folders_chat_ids(monkeypatch, dummy_folder_peers_cls):
    folders = [dummy_folder_peers_cls("F1", [1, 2])]

    async def fake_list_folders():
        return folders

    monkeypatch.setattr(main, "list_folders", fake_list_folders)

    from telethon import types

    chat_ids = await main.get_folders_chat_ids(["F1"])
    expected = {
        main.get_peer_id(types.PeerChannel(1)),
        main.get_peer_id(types.PeerChannel(2)),
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

    async def fake_get_input_entity(cid):
        from telethon import types

        return types.InputPeerChat(cid)

    client = SimpleNamespace(get_input_entity=fake_get_input_entity)

    monkeypatch.setattr(main, "client", client)
    monkeypatch.setattr(main, "get_folders_chat_ids", fake_get_folders_chat_ids)
    monkeypatch.setattr(main, "resolve_entities", fake_resolve_entities)

    inst = main.Instance(
        name="i", words=[], target_chat=0, folders=["f"], chat_ids={4}, entities=["e"]
    )

    await main.update_instance_chat_ids(inst, True)
    assert inst.chat_ids == {-4, -5, -6}


@pytest.mark.asyncio
async def test_get_folders_chat_ids_channel(monkeypatch):
    from telethon import types

    channel = types.InputPeerChannel(1, 2)
    folder = SimpleNamespace(title="F1", include_peers=[channel])

    async def fake_list_folders():
        return [folder]

    monkeypatch.setattr(main, "list_folders", fake_list_folders)

    chat_ids = await main.get_folders_chat_ids(["F1"])
    expected = {main.get_peer_id(types.PeerChannel(1))}
    assert chat_ids == expected


@pytest.mark.asyncio
async def test_get_folders_chat_ids_chat_and_user(monkeypatch):
    from telethon import types

    chat = types.InputPeerChat(7)
    user = types.InputPeerUser(8, 1)
    folder = SimpleNamespace(title="F2", include_peers=[chat, user])

    async def fake_list_folders():
        return [folder]

    monkeypatch.setattr(main, "list_folders", fake_list_folders)

    chat_ids = await main.get_folders_chat_ids(["F2"])
    expected = {
        main.get_peer_id(types.PeerChat(7)),
        main.get_peer_id(types.PeerUser(8)),
    }
    assert chat_ids == expected
