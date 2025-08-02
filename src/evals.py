from pathlib import Path

from .telegram_utils import get_safe_name


def get_eval_path(instance_name: str, prompt_name: str, suffix: str) -> Path:
    """Return base path for evaluation data."""
    inst = get_safe_name(instance_name)
    prm = get_safe_name(prompt_name)
    return Path("data") / "evals" / f"{inst}_{prm}_{suffix}"
