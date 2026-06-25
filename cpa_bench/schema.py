"""Task schema for CPA-Bench.

Each task is self-describing: it carries not just the question and gold
answer, but *how it should be graded* (``eval_method``). That field is what
lets the runner stay dumb — it dispatches each task to the right scorer
without knowing any accounting.

The schema is intentionally a superset of FinanceBench's, with the
accounting-specific fields the project is built around
(``accounting_role``, ``complexity``, ``required_reasoning``). Fields not
relevant to a given task can be omitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Supported grading methods. See cpa_bench/scorers.py for each implementation.
EVAL_METHODS = ("numeric", "exact", "mcq", "llm_judge")


@dataclass
class Task:
    """One benchmark item."""

    id: str
    question: str
    gold_answer: str
    eval_method: str  # one of EVAL_METHODS

    # Context handed to the model (the evidence excerpt, trial balance,
    # transaction log, etc.). Empty string = closed-book.
    context: str = ""

    # Parameters for the scorer, e.g. {"tolerance": 0.01} for numeric,
    # or {"choices": ["a", "b", ...]} for mcq.
    eval_params: dict[str, Any] = field(default_factory=dict)

    # Used by the llm_judge scorer to ground its decision.
    gold_rationale: str = ""

    # Provenance / taxonomy. Not used by scoring, but sliced in reporting.
    source: str = "unknown"            # e.g. "financebench", "synthetic"
    accounting_role: str = ""          # bookkeeper | staff_accountant | controller | auditor | analyst
    complexity: str = ""               # foundational | period_close | compliance | agentic | assurance
    required_reasoning: str = ""       # free-text label, e.g. "multi-step journal + adjustment"

    def __post_init__(self) -> None:
        if self.eval_method not in EVAL_METHODS:
            raise ValueError(
                f"task {self.id!r}: unknown eval_method {self.eval_method!r}; "
                f"expected one of {EVAL_METHODS}"
            )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Task":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"task {d.get('id')!r}: unexpected fields {sorted(unknown)}")
        return cls(**d)
