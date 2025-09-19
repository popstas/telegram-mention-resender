import pytest

import src.config as config


def test_load_config_success(tmp_path, monkeypatch):
    cfg_file = tmp_path / "cfg.yml"
    cfg_file.write_text("foo: 1")
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_file))
    assert config.load_config() == {"foo": 1}


def test_load_config_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "nonexistent.yml"))
    with pytest.raises(FileNotFoundError):
        config.load_config()


def test_get_api_credentials_success():
    cfg = {"api_id": "123", "api_hash": "hash", "session": "sess"}
    assert config.get_api_credentials(cfg) == (123, "hash", "sess")


def test_get_api_credentials_missing():
    with pytest.raises(RuntimeError):
        config.get_api_credentials({})


def test_config_path_env_override(tmp_path, monkeypatch):
    cfg = tmp_path / "env.yml"
    cfg.write_text("bar: 2")
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    import importlib

    cfg_module = importlib.reload(config)
    assert cfg_module.CONFIG_PATH == str(cfg)
    assert cfg_module.load_config() == {"bar": 2}


@pytest.mark.asyncio
async def test_load_instances_folder_add_topic():
    cfg = {
        "instances": [
            {
                "name": "inst",
                "words": [],
                "folder_add_topic": [
                    {"name": "Topic", "message": "hello", "username": "user"}
                ],
            }
        ]
    }

    instances = await config.load_instances(cfg)
    assert instances[0].folder_add_topic
    topic = instances[0].folder_add_topic[0]
    assert topic.name == "Topic"
    assert topic.message == "hello"
    assert topic.username == "user"
