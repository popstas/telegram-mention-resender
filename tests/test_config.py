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
