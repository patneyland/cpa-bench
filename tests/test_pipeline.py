"""Offline tests — the testing protocol in code form.

These run the full harness through the MockClient: no network, no key, no
cost. They prove the runner, every scorer, and the reporting path work
before you ever spend a token on a real run.

Run with:  python -m pytest -q   (or: python tests/test_pipeline.py)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cpa_bench.client import MockClient
from cpa_bench.config import RunConfig, load_tasks
from cpa_bench.runner import run
from cpa_bench.scorers import score
from cpa_bench.schema import Task


def _task(**kw) -> Task:
    base = dict(id="t", question="q", gold_answer="1", eval_method="numeric")
    base.update(kw)
    return Task.from_dict(base)


def test_numeric_scorer_tolerance():
    t = _task(eval_method="numeric", gold_answer="2.50", eval_params={"tolerance": 0.01})
    assert score(t, "reasoning...\nFINAL ANSWER: 2.50").correct
    assert score(t, "FINAL ANSWER: 2.51").correct        # within 1%
    assert not score(t, "FINAL ANSWER: 3.00").correct


def test_numeric_handles_currency_and_parens():
    t = _task(eval_method="numeric", gold_answer="-1500")
    assert score(t, "FINAL ANSWER: $(1,500)").correct    # accounting negative


def test_exact_scorer_normalizes():
    t = _task(eval_method="exact", gold_answer="Rent expense")
    assert score(t, "FINAL ANSWER: rent expense.").correct
    assert not score(t, "FINAL ANSWER: utilities expense").correct


def test_mcq_scorer():
    t = _task(eval_method="mcq", gold_answer="a")
    assert score(t, "FINAL ANSWER: a").correct
    assert score(t, "FINAL ANSWER: a) Debit Insurance Expense").correct
    assert not score(t, "FINAL ANSWER: b").correct


def test_llm_judge_uses_client():
    t = _task(eval_method="llm_judge", gold_answer="$0", gold_rationale="deferred revenue")
    yes = MockClient(canned="CORRECT - matches the gold conclusion.")
    no = MockClient(canned="INCORRECT - wrong period.")
    assert score(t, "FINAL ANSWER: $0", yes, "judge/model").correct
    assert not score(t, "FINAL ANSWER: $120,000", no, "judge/model").correct


def test_full_run_offline(tmp_path):
    tasks = load_tasks("data/sample_tasks.jsonl")
    cfg = RunConfig(models=["mock/model-a", "mock/model-b"], judge="mock/judge", concurrency=4)
    client = MockClient(canned="FINAL ANSWER: 2.50")
    judge = MockClient(canned="CORRECT")
    summary = run(cfg, tasks, client, str(tmp_path), judge_client=judge)
    # both models attempted every task; outputs + leaderboard exist
    assert set(summary) == {"mock/model-a", "mock/model-b"}
    for s in summary.values():
        assert s["n"] == len(tasks)
    assert (tmp_path / "leaderboard.md").exists()
    assert (tmp_path / "scores.jsonl").exists()


if __name__ == "__main__":
    import tempfile

    test_numeric_scorer_tolerance()
    test_numeric_handles_currency_and_parens()
    test_exact_scorer_normalizes()
    test_mcq_scorer()
    test_llm_judge_uses_client()
    with tempfile.TemporaryDirectory() as d:
        test_full_run_offline(__import__("pathlib").Path(d))
    print("all offline tests passed")
