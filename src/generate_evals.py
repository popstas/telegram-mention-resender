import argparse
import asyncio
import json
from typing import Iterable

from telethon import TelegramClient

from .config import get_api_credentials, load_config, load_instances
from .evals import get_eval_path
from .telegram_utils import get_safe_name
from .trace_ids import trace_ids


async def _fetch_messages(client: TelegramClient, entity) -> Iterable:
    """Yield messages from ``entity`` that contain text."""
    async for msg in client.iter_messages(entity):
        text = (
            getattr(msg, "message", None)
            or getattr(msg, "text", None)
            or getattr(msg, "raw_text", None)
        )
        if text:
            yield msg


async def generate_evals(suffix: str) -> None:
    """Generate evaluation datasets from true/false positive entities."""
    config = load_config()
    api_id, api_hash, session = get_api_credentials(config)
    client = TelegramClient(session, api_id, api_hash)
    await client.start()

    instances = await load_instances(config)

    for inst in instances:
        if not inst.true_positive_entity or not inst.false_positive_entity:
            continue
        for prompt in inst.prompts:
            base = get_eval_path(inst.name, prompt.name or "prompt", suffix)
            base.mkdir(parents=True, exist_ok=True)

            inst_name = get_safe_name(inst.name)
            prompt_name = get_safe_name(prompt.name or "prompt")

            msg_path = base / "messages.jsonl"
            with msg_path.open("w", encoding="utf-8") as fh:
                async for msg in _fetch_messages(client, inst.true_positive_entity):
                    text = (
                        getattr(msg, "message", None)
                        or getattr(msg, "text", None)
                        or getattr(msg, "raw_text", None)
                    )
                    fh.write(
                        json.dumps(
                            {
                                "input": text,
                                "expected": {"is_match": True},
                                "trace_id": trace_ids.get(msg.id),
                            },
                            ensure_ascii=False,
                        )
                        + "\n",
                    )
                async for msg in _fetch_messages(client, inst.false_positive_entity):
                    text = (
                        getattr(msg, "message", None)
                        or getattr(msg, "text", None)
                        or getattr(msg, "raw_text", None)
                    )
                    fh.write(
                        json.dumps(
                            {
                                "input": text,
                                "expected": {"is_match": False},
                                "trace_id": trace_ids.get(msg.id),
                            },
                            ensure_ascii=False,
                        )
                        + "\n",
                    )

            model = (prompt.config or {}).get("model", "gpt-4.1")
            temperature = (prompt.config or {}).get("temperature", 0.2)
            task_yml = f"""eval_name: {inst_name}_{prompt_name}
dataset: ./messages.jsonl

model: {model}
modelParameters:
  temperature: {temperature}
  response_format: {{ type: json_schema }}
messages:
  - role: system
    content: |
      {prompt.prompt or ''}
  - role: user
    content: |
      {{input}}

task: llm-rubric
rubric: |
  import json
  def grade(resp, expected):
      score = json.loads(resp)["score"]
      pred  = score >= {prompt.threshold}
      return {{"accuracy": int(pred == expected["is_match"])}}
metrics: [accuracy]
"""
            (base / "task.yml").write_text(task_yml, encoding="utf-8")

            readme = f"""# Evaluation for {inst.name} - {prompt.name}

To run this evaluation:

```bash
python -m src.run_openai_evals --instance \"{inst.name}\" --prompt \"{prompt.name}\" --suffix {suffix}
```
"""
            (base / "README.md").write_text(readme, encoding="utf-8")

    await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate evaluation datasets")
    parser.add_argument("--suffix", required=True, help="Folder suffix")
    args = parser.parse_args()
    asyncio.run(generate_evals(args.suffix))


if __name__ == "__main__":
    main()
