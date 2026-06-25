"""Judge validation.

The benchmark uses an LLM to grade open-ended (``llm_judge``) tasks. That
judge has its own error rate, so before any ``llm_judge`` score can be
trusted we must measure how often the judge agrees with humans.

This module runs the *deployed* judge (cpa_bench.scorers.judge_verdict) over
a labeled set of ``(question, gold, candidate, human_label)`` items and
reports:

* overall agreement,
* Cohen's kappa (agreement corrected for chance),
* a confusion matrix, and
* the **false-pass rate** — how often the judge calls a wrong answer
  correct. That is the dangerous failure: it silently inflates model
  scores. We surface it first.

Sliced by accounting_role and complexity so weaknesses are visible.

A labeled item (one JSON object per line in a .jsonl file):

    {
      "task_id": "...",
      "question": "...",
      "gold_answer": "...",
      "gold_rationale": "...",
      "candidate_answer": "...",        # the answer being graded
      "human_label": "correct"|"incorrect",
      "accounting_role": "...",         # optional, for slicing
      "complexity": "...",              # optional
      "candidate_source": "synthetic"|"model:<name>"   # optional provenance
    }
"""

from __future__ import annotations

import json
from collections import defaultdict

from .scorers import judge_verdict

REQUIRED_FIELDS = ("task_id", "question", "gold_answer", "candidate_answer", "human_label")


def load_items(path: str) -> list[dict]:
    items: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            missing = [f for f in REQUIRED_FIELDS if f not in d or d[f] == ""]
            if missing:
                raise ValueError(f"{path}:{ln}: item missing/blank fields {missing}")
            label = str(d["human_label"]).strip().lower()
            if label not in ("correct", "incorrect"):
                raise ValueError(
                    f"{path}:{ln}: human_label must be 'correct' or 'incorrect', got {d['human_label']!r}"
                )
            items.append(d)
    return items


def run_judge_eval(items: list[dict], judge_client, judge_model: str) -> list[dict]:
    """Grade each labeled candidate with the deployed judge. Sequential on
    purpose — validation sets are small and determinism aids debugging."""
    records: list[dict] = []
    for it in items:
        ok, detail = judge_verdict(
            judge_client,
            judge_model,
            it["question"],
            it["gold_answer"],
            it.get("gold_rationale", ""),
            it["candidate_answer"],
        )
        human = str(it["human_label"]).strip().lower() == "correct"
        records.append(
            {
                "task_id": it["task_id"],
                "accounting_role": it.get("accounting_role", ""),
                "complexity": it.get("complexity", ""),
                "candidate_source": it.get("candidate_source", ""),
                "human_correct": human,
                "judge_correct": ok,
                "agree": ok == human,
                "judge_detail": detail,
            }
        )
    return records


def _cohen_kappa(tp: int, fp: int, fn: int, tn: int) -> float:
    n = tp + fp + fn + tn
    if n == 0:
        return 0.0
    p_o = (tp + tn) / n
    # marginal probabilities for the two raters over {correct, incorrect}
    judge_c = (tp + fp) / n
    human_c = (tp + fn) / n
    p_e = judge_c * human_c + (1 - judge_c) * (1 - human_c)
    if abs(1 - p_e) < 1e-12:
        return 1.0 if abs(p_o - 1.0) < 1e-12 else 0.0
    return (p_o - p_e) / (1 - p_e)


def metrics(records: list[dict]) -> dict:
    n = len(records)
    # positive class = "correct"
    tp = sum(1 for r in records if r["judge_correct"] and r["human_correct"])
    fp = sum(1 for r in records if r["judge_correct"] and not r["human_correct"])
    fn = sum(1 for r in records if not r["judge_correct"] and r["human_correct"])
    tn = sum(1 for r in records if not r["judge_correct"] and not r["human_correct"])
    agree = tp + tn
    human_wrong = fp + tn  # candidates humans marked incorrect

    out = {
        "n": n,
        "agreement": agree / n if n else 0.0,
        "cohen_kappa": _cohen_kappa(tp, fp, fn, tn),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        # The two error modes, named for what they do to the benchmark:
        # false_pass = judge accepted an answer humans rejected (inflates scores)
        "false_pass": fp,
        "false_pass_rate": (fp / human_wrong) if human_wrong else 0.0,
        # false_fail = judge rejected an answer humans accepted (deflates scores)
        "false_fail": fn,
        "false_fail_rate": (fn / (tp + fn)) if (tp + fn) else 0.0,
        "by_role": _slice(records, "accounting_role"),
        "by_complexity": _slice(records, "complexity"),
    }
    return out


def _slice(records: list[dict], key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r.get(key) or "(unset)"].append(r)
    return {
        g: {"n": len(rs), "agreement": sum(1 for r in rs if r["agree"]) / len(rs)}
        for g, rs in sorted(groups.items())
    }


def render_report(m: dict, judge_model: str) -> str:
    lines = [
        "# CPA-Bench — judge validation report",
        "",
        f"Judge model: `{judge_model}`",
        f"Labeled items: {m['n']}",
        "",
        f"- **Agreement with humans:** {m['agreement']:.1%}",
        f"- **Cohen's kappa:** {m['cohen_kappa']:.3f}",
        f"- **False-pass** (judge accepted a wrong answer): "
        f"{m['false_pass']} ({m['false_pass_rate']:.1%} of human-incorrect items)",
        f"- **False-fail** (judge rejected a correct answer): "
        f"{m['false_fail']} ({m['false_fail_rate']:.1%} of human-correct items)",
        "",
        "Confusion matrix (positive = 'correct'):",
        "",
        "| | human: correct | human: incorrect |",
        "|---|---|---|",
        f"| judge: correct | {m['confusion']['tp']} (TP) | {m['confusion']['fp']} (FP) |",
        f"| judge: incorrect | {m['confusion']['fn']} (FN) | {m['confusion']['tn']} (TN) |",
        "",
        "## Agreement by accounting role",
        "",
        "| Role | N | Agreement |",
        "|---|---|---|",
    ]
    for g, s in m["by_role"].items():
        lines.append(f"| {g} | {s['n']} | {s['agreement']:.1%} |")
    lines += ["", "## Agreement by complexity", "", "| Complexity | N | Agreement |", "|---|---|---|"]
    for g, s in m["by_complexity"].items():
        lines.append(f"| {g} | {s['n']} | {s['agreement']:.1%} |")
    lines.append("")
    return "\n".join(lines)


def prep_template(scores_path: str, tasks_path: str, out_path: str) -> int:
    """Build a labeling template from a completed run: extract every
    llm_judge candidate answer, join task text, and emit items with a blank
    human_label for a CPA to fill in. This is how a real (non-synthetic)
    validation set gets created."""
    import json as _json

    tasks = {}
    for line in open(tasks_path, encoding="utf-8"):
        line = line.strip()
        if line:
            t = _json.loads(line)
            tasks[t["id"]] = t

    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for line in open(scores_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            rec = _json.loads(line)
            if rec.get("eval_method") != "llm_judge":
                continue
            t = tasks.get(rec["task_id"])
            if not t:
                continue
            item = {
                "task_id": rec["task_id"],
                "question": t["question"],
                "gold_answer": t["gold_answer"],
                "gold_rationale": t.get("gold_rationale", ""),
                "candidate_answer": rec.get("parsed_answer", ""),
                "human_label": "",  # <-- CPA fills this: "correct" or "incorrect"
                "accounting_role": t.get("accounting_role", ""),
                "complexity": t.get("complexity", ""),
                "candidate_source": f"model:{rec.get('model', '')}",
            }
            out.write(_json.dumps(item) + "\n")
            n += 1
    return n
