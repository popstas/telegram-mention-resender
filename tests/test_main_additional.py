import asyncio
import os
from types import SimpleNamespace

import pytest

import src.main as main


# ---------- load_config ----------

def test_load_config_success(tmp_path, monkeypatch):
    cfg_file = tmp_path / "cfg.yml"
    cfg_file.write_text("foo: 1")
    monkeypatch.setattr(main, "CONFIG_PATH", str(cfg_file))
    assert main.load_config() == {"foo": 1}


def test_load_config_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "CONFIG_PATH", str(tmp_path / "nonexistent.yml"))
    with pytest.raises(FileNotFoundError):
        main.load_config()


# ---------- get_api_credentials ----------

def test_get_api_credentials_success():
    cfg = {"api_id": "123", "api_hash": "hash", "session": "sess"}
    assert main.get_api_credentials(cfg) == (123, "hash", "sess")


def test_get_api_credentials_missing():
    with pytest.raises(RuntimeError):
        main.get_api_credentials({})


# ---------- get_folder ----------
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
    folders = [DummyFolder("Other")]  # title not matching
    result = await main.get_folder(folders, "Missing")
    assert result is None


# ---------- get_folders_chat_ids ----------
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


# ---------- update_instance_chat_ids ----------
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
    assert inst.chat_ids == {4,5,6}


# ---------- get_entity_name error path ----------
@pytest.mark.asyncio
async def test_get_entity_name_error(monkeypatch):
    class FailClient:
        async def get_entity(self, ident):
            raise RuntimeError("fail")

    main.client = FailClient()
    main.entity_name_cache.clear()

    name = await main.get_entity_name("https://t.me/testchat?param=1")
    assert name == "testchat"
