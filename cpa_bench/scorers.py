"""Scorers — one per eval_method.

A scorer takes a Task and the model's raw text and returns a Score. The
deterministic scorers (numeric, exact, mcq) need no model. The llm_judge
scorer needs a client + judge model, supplied by the runner.

This is the part of the harness where the real engineering lives. Grading
accounting work is harder than grading trivia: numbers need tolerance,
answers can be phrased many ways, and open-ended judgment needs a model
referee that must itself be validated against humans. Start simple and
honest; tighten over time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import Task

FINAL_ANSWER_RE = re.compile(r"FINAL ANSWER:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)


@dataclass
class Score:
    correct: bool
    detail: str = ""          # human-readable explanation of the verdict
    parsed_answer: str = ""   # what we extracted from the model output


def extract_final_answer(text: str) -> str:
    """Pull the value after the FINAL ANSWER tag; fall back to last line."""
    m = FINAL_ANSWER_RE.search(text or "")
    if m:
        return m.group(1).strip()
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# ---- deterministic scorers -------------------------------------------------

_NUM_RE = re.compile(r"-?\$?\(?\d[\d,]*\.?\d*\)?%?")


def _to_number(s: str) -> float | None:
    m = _NUM_RE.search(s.replace(",", "") if s else "")
    if not m:
        return None
    tok = m.group(0)
    # Accounting negatives are shown in parentheses, sometimes after a '$'.
    neg = ("(" in tok) or tok.lstrip().startswith("-")
    tok = tok.replace("$", "").replace("(", "").replace(")", "").replace("%", "").replace("-", "").strip()
    try:
        val = float(tok)
    except ValueError:
        return None
    return -val if neg else val


def score_numeric(task: Task, model_text: str) -> Score:
    ans = extract_final_answer(model_text)
    got = _to_number(ans)
    gold = _to_number(task.gold_answer)
    if got is None or gold is None:
        return Score(False, f"could not parse number (got={ans!r}, gold={task.gold_answer!r})", ans)
    tol = float(task.eval_params.get("tolerance", 0.01))  # default 1% relative
    denom = abs(gold) if gold != 0 else 1.0
    ok = abs(got - gold) / denom <= tol
    return Score(ok, f"got={got} gold={gold} rel_tol={tol}", ans)


def score_exact(task: Task, model_text: str) -> Score:
    ans = extract_final_answer(model_text)
    norm = lambda s: re.sub(r"\s+", " ", s.strip().lower().rstrip("."))
    ok = norm(ans) == norm(task.gold_answer)
    return Score(ok, f"got={ans!r} gold={task.gold_answer!r}", ans)


def score_mcq(task: Task, model_text: str) -> Score:
    ans = extract_final_answer(model_text).strip().lower()
    gold = task.gold_answer.strip().lower()
    # accept "b" or "b) ..." style; compare leading token
    ans_key = ans.split(")")[0].split(".")[0].strip()
    ok = ans_key == gold or ans == gold
    return Score(ok, f"got={ans_key!r} gold={gold!r}", ans)


# ---- model-graded scorer ---------------------------------------------------

JUDGE_SYSTEM = (
    "You are a strict accounting grader. You are given a question, the "
    "reference (gold) answer, the reference rationale, and a candidate "
    "answer. Decide whether the candidate is correct: it must reach the "
    "same conclusion as the gold answer and not contain disqualifying "
    "errors. Minor wording differences are fine. Respond with exactly "
    "'CORRECT' or 'INCORRECT' on the first line, then one sentence of "
    "justification."
)


def build_judge_prompt(question: str, gold_answer: str, gold_rationale: str, candidate: str) -> str:
    return (
        f"QUESTION:\n{question}\n\n"
        f"GOLD ANSWER:\n{gold_answer}\n\n"
        f"GOLD RATIONALE:\n{gold_rationale or '(none provided)'}\n\n"
        f"CANDIDATE ANSWER:\n{candidate}\n\n"
        "Is the candidate correct? Reply CORRECT or INCORRECT."
    )


def judge_verdict(
    judge_client, judge_model: str, question: str, gold_answer: str,
    gold_rationale: str, candidate: str,
) -> tuple[bool, str]:
    """Run the deployed judge on one (question, gold, candidate) and return
    (is_correct, detail). This is the single source of truth for judging —
    both the benchmark scorer and the validation harness call it, so the
    judge we validate is exactly the judge we ship."""
    user = build_judge_prompt(question, gold_answer, gold_rationale, candidate)
    result = judge_client.complete(judge_model, JUDGE_SYSTEM, user)
    if result.error:
        return False, f"judge error: {result.error}"
    verdict = (result.text or "").strip().upper()
    ok = verdict.startswith("CORRECT")
    return ok, f"judge={(result.text or '').strip()[:160]!r}"


def score_llm_judge(task: Task, model_text: str, judge_client, judge_model: str) -> Score:
    ans = extract_final_answer(model_text)
    ok, detail = judge_verdict(
        judge_client, judge_model, task.question, task.gold_answer, task.gold_rationale, ans
    )
    return Score(ok, detail, ans)


def score(task: Task, model_text: str, judge_client=None, judge_model: str = "") -> Score:
    """Dispatch a task to its scorer based on eval_method."""
    if task.eval_method == "numeric":
        return score_numeric(task, model_text)
    if task.eval_method == "exact":
        return score_exact(task, model_text)
    if task.eval_method == "mcq":
        return score_mcq(task, model_text)
    if task.eval_method == "llm_judge":
        if judge_client is None:
            raise ValueError("llm_judge task requires a judge client")
        return score_llm_judge(task, model_text, judge_client, judge_model)
    raise ValueError(f"no scorer for eval_method {task.eval_method!r}")
