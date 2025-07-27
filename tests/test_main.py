import asyncio
from types import SimpleNamespace

import pytest

import src.main as main


def test_word_in_text_basic():
    words = ["hello", "world"]
    assert main.word_in_text(words, "Hello there") is True
    assert main.word_in_text(words, "no match") is False


class DummyMessage:
    def __init__(self, peer_id):
        self.peer_id = peer_id
        self.id = 123


def test_get_message_url_object_peer():
    peer = SimpleNamespace(channel_id=42)
    msg = DummyMessage(peer)
    assert main.get_message_url(msg) == "https://t.me/c/42/123"


def test_get_message_url_dict_peer():
    peer = {"channel_id": 7}
    msg = DummyMessage(peer)
    assert main.get_message_url(msg) == "https://t.me/c/7/123"


def test_load_instances_direct():
    config = {
        "instances": [
            {
                "name": "test",
                "folders": ["f"],
                "chat_ids": [1],
                "entities": ["e"],
                "words": ["w"],
                "target_chat": 2,
            }
        ]
    }
    instances = asyncio.run(main.load_instances(config))
    assert len(instances) == 1
    inst = instances[0]
    assert inst.name == "test"
    assert inst.folders == ["f"]
    assert inst.chat_ids == {1}
    assert inst.entities == ["e"]
    assert inst.words == ["w"]
    assert inst.target_chat == 2


def test_load_instances_backward_compat():
    config = {
        "folders": ["f"],
        "chat_ids": [1],
        "entities": ["e"],
        "words": ["w"],
        "target_chat": 2,
    }
    instances = asyncio.run(main.load_instances(config))
    assert len(instances) == 1
    inst = instances[0]
    assert inst.folders == ["f"]
    assert inst.chat_ids == {1}
    assert inst.entities == ["e"]
    assert inst.words == ["w"]
    assert inst.target_chat == 2


