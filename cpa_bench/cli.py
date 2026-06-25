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

import json
import os

from . import config, judge_eval
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


def cmd_judge_eval(args: argparse.Namespace) -> int:
    cfg = config.load_models(args.models)
    judge_model = args.judge or cfg.judge
    items = judge_eval.load_items(args.items)
    if args.limit:
        items = items[: args.limit]
    if not items:
        print("No labeled items loaded.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"DRY RUN: judging {len(items)} item(s) with a mock judge (no API calls).")
        # MockClient always says CORRECT, so dry-run only proves the plumbing,
        # not the judge quality. Real numbers need --no-dry-run + a key.
        judge_client = MockClient(canned="CORRECT (dry-run mock judge)")
    else:
        judge_client = OpenRouterClient(config.openrouter_key(required=True))

    records = judge_eval.run_judge_eval(items, judge_client, judge_model)
    m = judge_eval.metrics(records)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "judge_records.jsonl"), "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    report = judge_eval.render_report(m, judge_model)
    with open(os.path.join(args.out, "judge_report.md"), "w", encoding="utf-8") as fh:
        fh.write(report)

    print()
    print(f"Judge: {judge_model}")
    print(f"Agreement with humans: {m['agreement']:.1%}   Cohen's kappa: {m['cohen_kappa']:.3f}")
    print(f"False-pass (accepted a wrong answer): {m['false_pass']}/{m['false_pass'] + m['confusion']['tn']}"
          f"  ({m['false_pass_rate']:.1%})")
    print(f"False-fail (rejected a correct answer): {m['false_fail']}/{m['false_fail'] + m['confusion']['tp']}"
          f"  ({m['false_fail_rate']:.1%})")
    print(f"\nWrote {args.out}/judge_report.md and judge_records.jsonl")
    return 0


def cmd_judge_prep(args: argparse.Namespace) -> int:
    n = judge_eval.prep_template(args.run, args.tasks, args.out)
    print(f"Wrote {n} labeling item(s) to {args.out}")
    print("Fill in each item's human_label ('correct' or 'incorrect'), then run:")
    print(f"  python -m cpa_bench.cli judge-eval --items {args.out}")
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

    je = sub.add_parser("judge-eval", help="measure the LLM judge's agreement with human labels")
    je.add_argument("--items", required=True, help="labeled judge-eval .jsonl (see data/judge_eval_seed.jsonl)")
    je.add_argument("--models", default="configs/models.yaml", help="path to models.yaml (for the judge model)")
    je.add_argument("--judge", default=None, help="override the judge model id")
    je.add_argument("--out", default="results/judge", help="output directory")
    je.add_argument("--limit", type=int, default=None, help="only the first N items (smoke test)")
    je.add_argument("--dry-run", action="store_true", help="no API calls; mock judge (plumbing check only)")
    je.set_defaults(func=cmd_judge_eval)

    jp = sub.add_parser("judge-prep", help="build a labeling template from a completed run for CPA review")
    jp.add_argument("--run", required=True, help="path to a run's scores.jsonl")
    jp.add_argument("--tasks", required=True, help="the tasks .jsonl used for that run")
    jp.add_argument("--out", default="data/judge_eval_to_label.jsonl", help="output labeling template")
    jp.set_defaults(func=cmd_judge_prep)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
