"""Offline tests for the judge-validation harness.

A scripted mock judge lets us drive an exact confusion matrix with no
network, so the metrics (agreement, Cohen's kappa, false-pass/false-fail)
are checked against hand-computed values.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cpa_bench.client import Completion
from cpa_bench import judge_eval


class ScriptedJudge:
    """Returns CORRECT/INCORRECT for each call in order. run_judge_eval is
    sequential, so the i-th verdict applies to the i-th item."""

    def __init__(self, verdicts: list[bool]):
        self._v = list(verdicts)
        self._i = 0

    def complete(self, model, system, user) -> Completion:
        ok = self._v[self._i]
        self._i += 1
        return Completion(text="CORRECT" if ok else "INCORRECT")


def _item(label: str, i: int) -> dict:
    return {
        "task_id": f"t{i}",
        "question": "q",
        "gold_answer": "g",
        "gold_rationale": "r",
        "candidate_answer": "c",
        "human_label": label,
        "accounting_role": "controller",
        "complexity": "compliance",
    }


def test_confusion_and_kappa_mixed():
    # human:   correct, correct, incorrect, incorrect
    # judge:   correct, incorrect, incorrect, correct
    items = [_item("correct", 0), _item("correct", 1), _item("incorrect", 2), _item("incorrect", 3)]
    judge = ScriptedJudge([True, False, False, True])
    recs = judge_eval.run_judge_eval(items, judge, "mock/judge")
    m = judge_eval.metrics(recs)
    assert m["confusion"] == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    assert abs(m["agreement"] - 0.5) < 1e-9
    assert abs(m["cohen_kappa"] - 0.0) < 1e-9
    assert m["false_pass"] == 1 and m["false_fail"] == 1


def test_perfect_agreement():
    items = [_item("correct", 0), _item("incorrect", 1)]
    judge = ScriptedJudge([True, False])
    m = judge_eval.metrics(judge_eval.run_judge_eval(items, judge, "mock/judge"))
    assert abs(m["agreement"] - 1.0) < 1e-9
    assert abs(m["cohen_kappa"] - 1.0) < 1e-9
    assert m["false_pass"] == 0 and m["false_fail"] == 0


def test_false_pass_is_the_dangerous_metric():
    # judge rubber-stamps everything correct -> every human-incorrect item is a false pass
    items = [_item("incorrect", 0), _item("incorrect", 1), _item("correct", 2)]
    judge = ScriptedJudge([True, True, True])
    m = judge_eval.metrics(judge_eval.run_judge_eval(items, judge, "mock/judge"))
    assert m["false_pass"] == 2
    assert abs(m["false_pass_rate"] - 1.0) < 1e-9  # accepted 2/2 wrong answers


def test_load_items_validates():
    import json
    import tempfile

    # bad human_label
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        fh.write(json.dumps({**_item("maybe", 0)}) + "\n")
        path = fh.name
    try:
        judge_eval.load_items(path)
        raise AssertionError("expected ValueError for bad human_label")
    except ValueError:
        pass
    finally:
        os.unlink(path)


def test_seed_file_is_valid_and_balanced():
    items = judge_eval.load_items("data/judge_eval_seed.jsonl")
    labels = [i["human_label"] for i in items]
    assert len(items) == 12
    assert labels.count("correct") == 4
    assert labels.count("incorrect") == 8  # 4 clearly wrong + 4 subtly wrong


if __name__ == "__main__":
    test_confusion_and_kappa_mixed()
    test_perfect_agreement()
    test_false_pass_is_the_dangerous_metric()
    test_load_items_validates()
    test_seed_file_is_valid_and_balanced()
    print("all judge-eval offline tests passed")
