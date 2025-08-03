import argparse
import asyncio
import json
import os

from openai import OpenAI

from .config import load_config, load_instances
from .evals import get_eval_path
from .prompts import EvaluateResult
from .telegram_utils import get_safe_name


def run_openai_evals(
    instance: str,
    prompt_name: str,
    suffix: str,
    *,
    config_path: str | None = None,
) -> str:
    """Run OpenAI evals on previously generated dataset.

    Returns report URL from the created eval run.
    """
    if config_path:
        os.environ["CONFIG_PATH"] = config_path
        from . import config as config_module

        config_module.CONFIG_PATH = config_path

    config = load_config()
    instances = asyncio.run(load_instances(config))

    inst = next((i for i in instances if i.name == instance), None)
    if inst is None:
        raise ValueError(f"Instance not found: {instance}")

    prompt = next((p for p in inst.prompts if p.name == prompt_name), None)
    if prompt is None:
        raise ValueError(f"Prompt '{prompt_name}' not found in instance '{instance}'")

    base = get_eval_path(inst.name, prompt.name or "prompt", suffix)
    data_path = base / "messages.jsonl"
    if not data_path.exists():
        raise FileNotFoundError(data_path)

    client = OpenAI(api_key=config.get("openai_api_key"))

    with data_path.open("rb") as fh:
        uploaded = client.files.create(file=fh, purpose="evals")

    eval_name = f"{get_safe_name(inst.name)}_{get_safe_name(prompt.name or 'prompt')}"

    eval_obj = client.evals.create(
        name=eval_name,
        data_source_config={
            "type": "custom",
            "item_schema": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"},
                    "expected": {
                        "type": "object",
                        "properties": {"is_match": {"type": "boolean"}},
                        "required": ["is_match"],
                    },
                },
                "required": ["input", "expected"],
            },
            "include_sample_schema": True,
        },
        testing_criteria=[
            {
                "type": "python",
                "name": "Threshold Accuracy",
                "input": "{{ sample.output_text }}",
                "reference": "{{ item.expected.is_match }}",
                "code": (
                    "import json\n"
                    "score=json.loads(input)['score']\n"
                    f"pred=score>={prompt.threshold}\n"
                    "return int(pred==reference)"
                ),
            }
        ],
    )

    ds = {
        "type": "completions",
        "model": (prompt.config or {}).get("model", "gpt-4.1"),
        "input_messages": {
            "type": "template",
            "template": [
                {"role": "system", "content": prompt.prompt or ""},
                {"role": "user", "content": "{{ item.input }}"},
            ],
        },
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "EvaluateResult",
                "schema": EvaluateResult.model_json_schema(),
            },
        },
        "source": {"type": "file_id", "id": uploaded.id},
    }
    temperature = (prompt.config or {}).get("temperature")
    if temperature is not None:
        ds["sampling_params"] = {"temperature": temperature}
    run = client.evals.runs.create(
        eval_obj.id,
        name=f"{eval_name} run",
        data_source=ds,
    )

    return getattr(run, "report_url", "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OpenAI evals on saved datasets")
    parser.add_argument("--config", help="Path to config.yml", default=None)
    parser.add_argument("--instance", required=True, help="Instance name")
    parser.add_argument("--prompt", required=True, help="Prompt name")
    parser.add_argument("--suffix", required=True, help="Dataset suffix")
    args = parser.parse_args()
    url = run_openai_evals(
        args.instance, args.prompt, args.suffix, config_path=args.config
    )
    if url:
        print(f"Report URL: {url}")


if __name__ == "__main__":
    main()
