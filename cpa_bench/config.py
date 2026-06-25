"""Configuration loading: the models list and the task file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import yaml

from .schema import Task


@dataclass
class RunConfig:
    """Everything a run needs, assembled from models.yaml + CLI flags."""

    models: list[str]
    judge: str
    concurrency: int = 8
    # The system prompt prepended to every task. Kept here so it is part of
    # the versioned, reproducible config rather than buried in code.
    system_prompt: str = (
        "You are taking an accounting and finance benchmark. Read the provided "
        "context and answer the question. Show brief reasoning, then end your "
        "reply with a line in the exact form:\nFINAL ANSWER: <answer>\n"
        "Put only the answer after the tag — a number, a short phrase, or the "
        "requested structured output."
    )


def load_models(path: str) -> RunConfig:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    models = raw.get("models") or []
    if not models:
        raise ValueError(f"{path}: 'models' list is empty")
    return RunConfig(
        models=list(models),
        judge=raw.get("judge", models[0]),
        concurrency=int(raw.get("concurrency", 8)),
        system_prompt=raw.get("system_prompt") or RunConfig.system_prompt,
    )


def load_tasks(path: str, limit: int | None = None) -> list[Task]:
    tasks: list[Task] = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            tasks.append(Task.from_dict(json.loads(line)))
            if limit is not None and len(tasks) >= limit:
                break
    return tasks


def load_env(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from a .env file into the environment if present.

    Variables already set in the real environment are left untouched (so an
    exported key always wins). Uses python-dotenv when installed, with a
    minimal built-in fallback so the harness works even before dependencies
    are installed."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(path, override=False)
        return
    except ImportError:
        pass
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def openrouter_key(required: bool = True) -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if required and not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Export it, or use --dry-run to "
            "exercise the pipeline with no API calls and no key."
        )
    return key
