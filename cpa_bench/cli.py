"""Command-line entrypoint.

    python -m cpa_bench run --models configs/models.yaml --tasks data/sample_tasks.jsonl --out results/run-001

Testing protocol (run these before any real run):

    # 1. Full pipeline, no network, no key, no cost — exercises runner + scorers + reporting.
    python -m cpa_bench run --tasks data/sample_tasks.jsonl --dry-run

    # 2. Cheap real smoke test — first 2 tasks against the real models/judge.
    python -m cpa_bench run --tasks data/sample_tasks.jsonl --limit 2
"""

from __future__ import annotations

import argparse
import sys

from . import config
from .client import MockClient, OpenRouterClient
from .runner import run


def _default_out() -> str:
    # No Date.now() determinism worries here — fine to stamp with a counter
    # by scanning existing dirs, but a simple fixed default keeps it obvious.
    return "results/latest"


def cmd_run(args: argparse.Namespace) -> int:
    cfg = config.load_models(args.models)
    tasks = config.load_tasks(args.tasks, limit=args.limit)
    if not tasks:
        print("No tasks loaded.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"DRY RUN: {len(cfg.models)} model(s) x {len(tasks)} task(s), no API calls.")
        client = MockClient()
        judge = MockClient(canned="CORRECT (dry-run mock judge)")
    else:
        key = config.openrouter_key(required=True)
        client = OpenRouterClient(key)
        judge = client  # judge goes through the same single credential

    summary = run(cfg, tasks, client, args.out, judge_client=judge)

    print("\n=== leaderboard ===")
    for model, s in sorted(summary.items(), key=lambda kv: -kv[1]["accuracy"]):
        print(f"{model:40s} {s['accuracy']:6.1%}  ({s['correct']}/{s['n']})  ${s['cost_usd']:.4f}")
    print(f"\nWrote results to {args.out}/  (leaderboard.md, scores.jsonl, raw/)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cpa_bench", description="CPA-Bench evaluation harness")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run models against tasks and score them")
    r.add_argument("--models", default="configs/models.yaml", help="path to models.yaml")
    r.add_argument("--tasks", required=True, help="path to tasks .jsonl")
    r.add_argument("--out", default=_default_out(), help="output directory")
    r.add_argument("--limit", type=int, default=None, help="only run the first N tasks (smoke test)")
    r.add_argument("--dry-run", action="store_true", help="no API calls; mock client (offline self-test)")
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
