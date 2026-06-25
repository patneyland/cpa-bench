"""The run loop: (model x task) -> output -> score -> results.

Writes everything under an output directory so a crash never loses work and
runs are reproducible:

    <out>/raw/<model>/<task_id>.json   one record per (model, task)
    <out>/scores.jsonl                 flat scored records
    <out>/leaderboard.md               aggregate accuracy + cost per model
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

from .config import RunConfig
from .schema import Task
from .scorers import score


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def build_prompt(task: Task) -> str:
    if task.context:
        return f"CONTEXT:\n{task.context}\n\nQUESTION:\n{task.question}"
    return f"QUESTION:\n{task.question}"


def run(
    cfg: RunConfig,
    tasks: list[Task],
    client,
    out_dir: str,
    judge_client=None,
) -> dict:
    """Execute every (model, task) pair and write results. Returns a summary."""
    os.makedirs(out_dir, exist_ok=True)
    raw_dir = os.path.join(out_dir, "raw")
    judge_client = judge_client or client

    records: list[dict] = []

    def work(model: str, task: Task) -> dict:
        prompt = build_prompt(task)
        completion = client.complete(model, cfg.system_prompt, prompt)
        if completion.error:
            sc = None
            correct = False
            detail = f"model error: {completion.error}"
            parsed = ""
        else:
            s = score(task, completion.text, judge_client, cfg.judge)
            correct, detail, parsed = s.correct, s.detail, s.parsed_answer
        rec = {
            "model": model,
            "task_id": task.id,
            "accounting_role": task.accounting_role,
            "complexity": task.complexity,
            "eval_method": task.eval_method,
            "correct": correct,
            "detail": detail,
            "parsed_answer": parsed,
            "model_text": completion.text,
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
            "cost_usd": completion.cost_usd,
            "error": completion.error,
        }
        # persist raw immediately
        mdir = os.path.join(raw_dir, _slug(model))
        os.makedirs(mdir, exist_ok=True)
        with open(os.path.join(mdir, f"{_slug(task.id)}.json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=2)
        return rec

    jobs = [(m, t) for m in cfg.models for t in tasks]
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        futures = [pool.submit(work, m, t) for m, t in jobs]
        for i, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            records.append(rec)
            mark = "ok " if rec["correct"] else "MISS"
            print(f"[{i}/{len(jobs)}] {mark} {rec['model']} :: {rec['task_id']}")

    # write flat scored records
    with open(os.path.join(out_dir, "scores.jsonl"), "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    summary = aggregate(records, cfg.models)
    with open(os.path.join(out_dir, "leaderboard.md"), "w", encoding="utf-8") as fh:
        fh.write(render_leaderboard(summary, len(tasks)))
    return summary


def aggregate(records: list[dict], models: list[str]) -> dict:
    by_model: dict[str, dict] = {}
    for m in models:
        rs = [r for r in records if r["model"] == m]
        n = len(rs)
        correct = sum(1 for r in rs if r["correct"])
        cost = sum(r["cost_usd"] for r in rs)
        errors = sum(1 for r in rs if r["error"])
        by_model[m] = {
            "n": n,
            "correct": correct,
            "accuracy": (correct / n) if n else 0.0,
            "cost_usd": cost,
            "errors": errors,
        }
    return by_model


def render_leaderboard(summary: dict, n_tasks: int) -> str:
    lines = [
        "# CPA-Bench leaderboard",
        "",
        f"Tasks per model: {n_tasks}",
        "",
        "| Model | Accuracy | Correct/N | Cost (USD) | Errors |",
        "|---|---|---|---|---|",
    ]
    for model, s in sorted(summary.items(), key=lambda kv: -kv[1]["accuracy"]):
        lines.append(
            f"| {model} | {s['accuracy']:.1%} | {s['correct']}/{s['n']} "
            f"| ${s['cost_usd']:.4f} | {s['errors']} |"
        )
    return "\n".join(lines) + "\n"
