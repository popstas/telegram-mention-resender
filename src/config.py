import os
from dataclasses import dataclass, field
from typing import List, Set

import yaml

from .prompts import Prompt

# Allow overriding config path via environment variable
CONFIG_PATH = os.environ.get("CONFIG_PATH", os.path.join("data", "config.yml"))


@dataclass
class FolderTopic:
    """Configuration for automatically created folder topics."""

    name: str
    message: str | None = None


@dataclass
class Instance:
    """Configuration for a single monitoring instance."""

    name: str
    words: List[str]
    negative_words: List[str] = field(default_factory=list)
    ignore_words: List[str] = field(default_factory=list)
    target_chat: int | None = None
    target_entity: str | None = None
    false_positive_entity: str | None = None
    true_positive_entity: str | None = None
    folders: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    chat_ids: Set[int] = field(default_factory=set)
    folder_mute: bool = False
    no_forward_message: bool = False
    prompts: List[Prompt] = field(default_factory=list)
    folder_add_topic: List[FolderTopic] = field(default_factory=list)


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
                    "negative_words": config.get("negative_words", []),
                    "ignore_words": config.get("ignore_words", []),
                    "target_chat": config.get("target_chat"),
                    "target_entity": config.get("target_entity"),
                    "false_positive_entity": config.get("false_positive_entity"),
                    "true_positive_entity": config.get("true_positive_entity"),
                    "no_forward_message": config.get("no_forward_message", False),
                }
            ]
        }

    parsed_instances: List[Instance] = []
    for inst_cfg in config.get("instances", []):
        raw_prompts = inst_cfg.get("prompts", [])
        parsed_prompts: List[Prompt] = []
        for p in raw_prompts:
            if isinstance(p, dict):
                parsed_prompts.append(
                    Prompt(
                        name=p.get("name"),
                        prompt=p.get("prompt"),
                        threshold=p.get("threshold", 4),
                        langfuse_name=p.get("langfuse_name"),
                        langfuse_label=p.get("langfuse_label", "latest"),
                        langfuse_version=p.get("langfuse_version"),
                        langfuse_type=p.get("langfuse_type", "text"),
                        config=p.get("config"),
                    )
                )
            else:
                parsed_prompts.append(Prompt(prompt=p))

        folder_topics: List[FolderTopic] = []
        for topic_cfg in inst_cfg.get("folder_add_topic", []):
            if not isinstance(topic_cfg, dict):
                continue
            name = topic_cfg.get("name")
            if not name:
                continue
            folder_topics.append(
                FolderTopic(
                    name=name,
                    message=topic_cfg.get("message"),
                )
            )

        instance = Instance(
            name=inst_cfg.get("name", "instance"),
            folders=inst_cfg.get("folders", []),
            chat_ids=set(inst_cfg.get("chat_ids", [])),
            entities=inst_cfg.get("entities", []),
            words=inst_cfg.get("words", []),
            negative_words=inst_cfg.get("negative_words", []),
            ignore_words=inst_cfg.get("ignore_words", []),
            target_chat=inst_cfg.get("target_chat"),
            target_entity=inst_cfg.get("target_entity"),
            false_positive_entity=inst_cfg.get("false_positive_entity"),
            true_positive_entity=inst_cfg.get("true_positive_entity"),
            folder_mute=inst_cfg.get("folder_mute", False),
            no_forward_message=inst_cfg.get("no_forward_message", False),
            prompts=parsed_prompts,
            folder_add_topic=folder_topics,
        )
        parsed_instances.append(instance)
    return parsed_instances
