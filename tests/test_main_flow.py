import asyncio
import logging
from types import SimpleNamespace

import pytest

import src.main as main


class BreakLoop(Exception):
    pass


@pytest.mark.asyncio
async def test_rescan_loop(monkeypatch):
    sleep_calls = []
    load_calls = []

    async def fake_sleep(t):
        sleep_calls.append(t)
        return None

    async def fake_update(inst, fr):
        raise BreakLoop

    def fake_load_config():
        load_calls.append(True)
        return {}

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main, "update_instance_chat_ids", fake_update)
    monkeypatch.setattr(main, "load_config", fake_load_config)

    inst = main.Instance(name="i", words=[], target_chat=0)
    with pytest.raises(BreakLoop):
        await main.rescan_loop(inst, interval=0)
    assert sleep_calls == [0]
    assert len(load_calls) == 1


@pytest.mark.asyncio
async def test_setup_logging(monkeypatch):
    recorded = {}

    def fake_basicConfig(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(logging, "basicConfig", fake_basicConfig)
    tele_logger = logging.getLogger("telethon")
    tele_logger.setLevel(logging.INFO)
    main.setup_logging("debug")
    assert recorded["level"] == logging.DEBUG
    assert tele_logger.level == logging.WARNING


@pytest.mark.asyncio
async def test_main_flow(monkeypatch, dummy_tg_client, dummy_message_cls):
    config = {"log_level": "info"}
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(main, "get_api_credentials", lambda cfg: (1, "h", "s"))

    dummy_client = dummy_tg_client
    monkeypatch.setattr(main, "TelegramClient", lambda s, a, b: dummy_client)

    async def fake_rescan(inst):
        return None

    monkeypatch.setattr(main, "rescan_loop", fake_rescan)

    async def fake_update(inst, fr):
        inst.chat_ids = {1}

    monkeypatch.setattr(main, "update_instance_chat_ids", fake_update)

    async def fake_load_instances(cfg):
        return [main.Instance(name="i", words=["hi"], target_chat=99)]

    monkeypatch.setattr(main, "load_instances", fake_load_instances)
    monkeypatch.setattr(main, "get_message_url", lambda m: "URL")

    async def fake_get_entity_name(v):
        return "name"

    monkeypatch.setattr(main, "get_entity_name", fake_get_entity_name)

    await main.main()
    assert main.config is config

    handler = dummy_client.on_handler
    msg = dummy_message_cls(SimpleNamespace(channel_id=1), msg_id=5, text="hi there")
    event = SimpleNamespace(message=msg, chat_id=1)
    await handler(event)
    assert msg.forwarded == [99]
    assert dummy_client.sent[0][0][0] == 99
