# CPA-Bench — Build Plan

CPA-Bench exists to give the accounting profession an honest, public map of what AI
can and cannot do across real accounting workflows — so accountants prepare for AI
rather than hide from it. The benchmark is the vehicle; the destination is a profession
that meets AI with clear eyes about where these tools are already trustworthy, where
they fail, and where a human must stay in the loop.

This document is the working build plan: concrete, phased, and honest. It assumes the
mission and design laid out in [`README.md`](README.md) and does not restate them. Read
that first for the *why*; this is the *how* and *in what order*.

The guiding sequence: **build a trustworthy measuring instrument first, then measure.**
Most of the early effort goes into tasks worth measuring and a grader we can defend —
not into running models. Start cheap (evidence/oracle mode, `--dry-run`, `--limit`)
and only scale spend once the instrument is validated.

---

## Current status — v0 harness (done)

The v0 evaluation harness is built and tested. What it delivers today:

- [x] **Single-credential design.** The only secret is `OPENROUTER_API_KEY`. OpenRouter
  is an OpenAI-compatible gateway, so one key reaches every candidate model *and* the
  LLM judge. No per-provider keys, no per-provider client code.
- [x] **Self-describing tasks.** Each task carries `eval_method`
  (`numeric` | `exact` | `mcq` | `llm_judge`) plus taxonomy fields
  (`accounting_role`, `complexity`, `required_reasoning`). The runner stays dumb and
  dispatches to the right scorer. See [`cpa_bench/schema.py`](cpa_bench/schema.py).
- [x] **Deterministic scorers + an LLM judge.** Numeric (with relative tolerance and
  accounting-negative/parenthesis handling), exact-match (normalized), MCQ, and an
  LLM-as-judge grounded on a gold rationale. See [`cpa_bench/scorers.py`](cpa_bench/scorers.py).
- [x] **Crash-safe concurrent runner.** Writes one `raw/<model>/<task>.json` per call
  (a crash loses nothing), a flat `scores.jsonl`, and a cost-aware `leaderboard.md`
  with *real* per-model cost from OpenRouter usage. See [`cpa_bench/runner.py`](cpa_bench/runner.py).
- [x] **Built-in testing protocol.** `--dry-run` (offline MockClient, no key/cost,
  exercises the whole pipeline), `--limit N` (cheap real smoke test), and offline unit
  tests covering every scorer end-to-end. See [`cpa_bench/cli.py`](cpa_bench/cli.py)
  and [`tests/test_pipeline.py`](tests/test_pipeline.py).
- [x] **Sample tasks across four roles and all four grading methods.** See
  [`data/sample_tasks.jsonl`](data/sample_tasks.jsonl).

What v0 does **not** yet have: a real expert-reviewed dataset, the FinanceBench subset
incorporated under its license, a validated judge, journal-entry-aware scoring, or
published baselines. That is what the phases below deliver.

---

## Phase 1 — Dataset expansion (v0.1 core)

**Goal:** replace sample tasks with a first real, expert-reviewed task set — ~50–150
tasks — spanning the role layers, so there is something honest to measure.

The task schema is the contract. New tasks must be valid `Task` records
([`cpa_bench/schema.py`](cpa_bench/schema.py)) and load through `config.load_tasks`.

- [ ] **Author tasks across the role layers**, weighted toward where v0 is thin:
  - [ ] `bookkeeper` — transaction classification, double-entry journal entries.
  - [ ] `staff_accountant` — accruals, deferrals, depreciation, trial-balance adjustments.
  - [ ] `controller` — GAAP/IFRS judgment, ASC 606 revenue recognition, error/fraud indicators.
  - [ ] `auditor` — sampling logic, analytical/variance review, risk assessment.
  - [ ] `analyst` — foundational analysis (seeded now, expanded via FinanceBench in Phase 2).
- [ ] **Every task carries a gold answer and a gold rationale.** The rationale is not
  optional polish — it is what grounds the judge and what a human reviewer checks against.
- [ ] **Expert review.** Each task is reviewed by a credentialed accountant before it
  enters the set. Record the reviewer (or reviewer initials) and review date in task
  provenance. A task without sign-off does not ship.
- [ ] **Data hygiene.** All data synthetic or anonymized — no confidential client
  material, ever (see the Disclaimer in [`README.md`](README.md)). Synthetic data is
  validated by an accountant for realism, not just internal consistency.
- [ ] **Schema extensions only if needed.** Candidates that may surface here:
  - structured `expected_output` typing for journal entries (debit/credit line items)
    rather than a flat `gold_answer` string;
  - a `reviewer` / `reviewed_on` provenance field;
  - an `accounting_standard` tag (e.g. `ASC 606`, `ASC 842`) for slicing results.
  Extend the dataclass conservatively; keep older tasks loadable. Any change is
  reflected in `from_dict` validation and the offline tests.
- [ ] **Per-role task-authoring guide** so contributors can add their specialty
  consistently (format, difficulty calibration, what makes a good rationale).

**Deliverable:** `data/v0.1_tasks.jsonl` (~50–150 reviewed tasks) + an authoring guide.

---

## Phase 2 — Incorporate the FinanceBench foundational subset

**Goal:** fold in FinanceBench's 150-question open subset as the `analyst`/foundational
layer, correctly attributed and licensed.

- [ ] **License handling — do not assume MIT.** FinanceBench's dataset is **CC BY-NC**.
  Incorporate it under those terms: attribution preserved, non-commercial use respected.
  Keep upstream data conceptually and (where practical) physically separate from
  CPA-Bench's own tasks so the differing licenses stay clear.
- [ ] **Attribution.** Complete `ATTRIBUTION.md` with the FinanceBench citation, BibTeX,
  and license notes (already stubbed in [`README.md`](README.md)). Finalize `LICENSE`:
  permissive for original CPA-Bench code, with dataset licensing that respects upstream
  CC BY-NC terms.
- [ ] **Convert to CPA-Bench tasks.** Map each FinanceBench item to a `Task`:
  `source: "financebench"`, `accounting_role: "analyst"`, `complexity: "foundational"`,
  gold evidence excerpt (~1.4K tokens) into `context`, appropriate `eval_method`
  (mostly `numeric` / `llm_judge`).
- [ ] **Two context modes.** Ship both the cheap **evidence/oracle mode** (gold excerpt
  in `context`) and a **long-context mode** (full filing, ~100K tokens) so the cost vs.
  capability tradeoff from [`README.md`](README.md) is measurable. Default to evidence
  mode for routine runs.

**Deliverable:** FinanceBench subset loadable as CPA-Bench tasks; `ATTRIBUTION.md` and
`LICENSE` finalized.

---

## Phase 3 — Judge validation (linchpin)

**Goal:** make the LLM-as-judge trustworthy — and publish *how* trustworthy. Any
`llm_judge` score is only as credible as the judge behind it. This is its own phase
because the agreement number is a headline trust metric, not an implementation detail.

- [x] **Harness scaffolded.** [`cpa_bench/judge_eval.py`](cpa_bench/judge_eval.py) runs
  the *deployed* judge (the same `judge_verdict` the benchmark uses) over a labeled set
  and reports agreement, Cohen's κ, a confusion matrix, and **false-pass / false-fail**
  rates, sliced by role and complexity. CLI: `judge-eval` (score a labeled set) and
  `judge-prep` (turn a real run into a CPA labeling template). Seeded with a 12-item
  synthetic labeled set ([`data/judge_eval_seed.jsonl`](data/judge_eval_seed.jsonl)) so it
  runs today; offline tests check the metrics against hand-computed confusion matrices.
- [ ] **Build a human-labeled validation set.** Sample model answers spanning the full
  outcome range (clearly right, clearly wrong, and borderline). Have one or more CPAs
  label each as correct/incorrect, blind to the judge's verdict. (`judge-prep` produces
  the template; replace the synthetic seed with real model answers.)
- [ ] **Measure agreement.** Compute judge-vs-CPA agreement (raw agreement and a
  chance-corrected statistic such as Cohen's κ). Break it out by `accounting_role` and
  `complexity` — the judge may be reliable on bookkeeping and shaky on ASC 606 judgment.
- [ ] **Publish the number.** Report judge agreement openly as a standing trust metric
  alongside the leaderboard. If a result depends on the judge, the judge's reliability
  travels with it. Re-validate whenever the judge model or prompt changes.
- [ ] **Iterate the judge prompt** ([`cpa_bench/scorers.py`](cpa_bench/scorers.py),
  `JUDGE_SYSTEM`) against the labeled set; consider a confidence/abstain path that flags
  low-agreement task types for mandatory human review rather than trusting the model.
- [ ] **Set a bar.** Define a minimum agreement threshold below which a task type is *not*
  graded by the judge (deterministic scoring or human grading only).

**Deliverable:** a published judge-agreement report (with κ, sliced by role/complexity)
and a hardened judge prompt. This number gates v0.1.

---

## Phase 4 — Scoring & robustness

**Goal:** make grading fair to correct answers expressed differently, and tight enough
that "correct" means correct. Accounting answers have many valid surface forms; naive
matching both over- and under-credits.

- [ ] **Journal-entry canonicalization.** Parse debit/credit line items into a canonical
  form and compare on structure (accounts, amounts, direction) rather than string match.
  Accept multiple correct account-name forms (e.g. "Rent Expense" = "Rent expense" =
  "Office Rent Expense" where appropriate) via a configurable synonym/alias map.
- [ ] **Numeric tolerance policy.** Document and standardize tolerance: relative vs.
  absolute, rounding conventions, units (thousands vs. dollars), and presentation of
  accounting negatives. Builds on the existing `score_numeric` tolerance handling.
- [ ] **Structured-output enforcement.** Strengthen answer extraction beyond the
  `FINAL ANSWER:` tag — optionally require JSON for structured tasks (journal entries,
  multi-part answers) so parsing is deterministic and a malformed answer is a clear miss,
  not a lucky regex hit.
- [ ] **Multiple-correct-answer grading.** For tasks with more than one defensible answer,
  support a set of acceptable golds (or rubric-based partial credit) rather than a single
  string. Decide and document the partial-credit policy.
- [ ] **Scorer regression tests.** Every new scoring rule gets an offline test in
  [`tests/test_pipeline.py`](tests/test_pipeline.py) before it ships.

**Deliverable:** journal-aware + multi-answer scoring, a written tolerance/normalization
policy, and expanded offline tests.

---

## Phase 5 — Baselines & publication

**Goal:** run a real panel and publish results + methodology, so the conversation about
AI in accounting becomes evidence-based.

- [ ] **Frontier + open panel.** Run a panel of frontier and open-weight models via the
  existing [`configs/models.yaml`](configs/models.yaml). Start in evidence mode (a few
  dollars for the 150-question subset); reserve long-context mode (~$50–150) for a
  deliberate comparison run.
- [ ] **Publish results and methodology.** Leaderboard sliced by `accounting_role` and
  `complexity` (not just one aggregate accuracy), the judge-agreement number from Phase 3,
  per-model cost, and the full method writeup. Honest about failure modes, not just wins.
- [ ] **Reproducibility.** Pin model IDs, the system prompt, the judge, and dataset
  version per published run so anyone can re-run it.
- [ ] **Optional: Hugging Face dataset release.** Release the CPA-Bench-original tasks
  (respecting FinanceBench's separate CC BY-NC terms for that subset) for discoverability.

**Deliverable:** a public results page + methodology; optional HF dataset card.

---

## Phase 6 — Agentic / long-horizon extensions (later)

**Goal:** move beyond single-shot QA into the multi-step work accountants actually do.
This is intentionally later — it depends on a validated single-shot foundation.

- [ ] **Tool use.** Give models calculation and ledger-query tools; measure whether tool
  access changes accuracy and cost.
- [ ] **Multi-period / long-horizon tasks.** Process transaction batches across months;
  bank, intercompany, and consolidation reconciliations.
- [ ] **Process scoring.** Score not just the final number but the procedure — does the
  model apply the right standard and show its work the way a trustworthy professional would.

**Deliverable:** an agentic task layer with tool use and trajectory-aware scoring.

---

## Additional components that should be considered

Cross-cutting ideas that don't slot neatly into one phase — captured here so they
aren't lost. Several feed Phase 5 reporting, but they're listed separately because
they change *what the benchmark measures*, not just when. The throughline is **AI
efficiency**: accuracy is necessary but not sufficient — the question a firm actually
faces is how *efficiently* a model or framework reaches a correct answer.

### Efficiency, not just accuracy — the cost–quality frontier

Most benchmarks rank by accuracy and ignore cost. That leaves out the decision real
firms make. CPA-Bench already captures the raw materials (per-call cost and token
counts from OpenRouter usage); turning them into first-class metrics is a genuine
competitive advantage for the benchmark itself.

- [ ] **Report efficiency metrics next to accuracy:** cost per *correct* answer
  ($/correct), tokens per task, accuracy-per-dollar, and latency / time-to-answer.
  "96.9% at $0.13 vs 96.9% at $0.26" is the real decision, not a footnote.
- [ ] **Publish the cost–quality frontier**, not a single-axis leaderboard — plot
  accuracy against cost (and against latency) so the Pareto-efficient configurations
  are visible. A cheaper model that ties a pricier one on accounting accuracy is the
  headline.
- [ ] **Effort / reasoning-budget sensitivity.** Where a model exposes a reasoning
  effort knob, sweep it and show how accuracy *and* cost move together — locate the
  point of diminishing returns per task type.

### Agentic-framework efficiency (beyond single models)

The same task can be attempted by a bare model or by an agentic scaffold (tool-use
loop, planner, calculator/ledger tools). The interesting question isn't only "did it
get it right" but **"how much did it spend — steps, tool calls, tokens, dollars,
wall-clock — to get there, and was the scaffold worth it?"**

- [ ] **Instrument agentic runs:** count tool calls, steps/turns, total tokens, cost,
  and latency per task — not just the final verdict.
- [ ] **Compare frameworks on identical tasks:** bare model vs. framework A vs.
  framework B, reported on the efficiency frontier. Does the scaffold buy accuracy,
  and at what cost multiple?
- [ ] **"Efficiency of success."** Among *successful* completions, report the
  distribution of cost/steps — succeeding cheaply and consistently beats succeeding
  expensively. (Pairs with Phase 6's agentic layer.)

### Reliability as an efficiency concern

- [ ] **Consistency under repetition.** Run a task N times; report pass-rate and cost
  variance. A model right 9/10 cheaply may beat one right 10/10 expensively — and a
  model right only *sometimes* is both an efficiency and a trust problem. (Requires
  deciding how scoring handles non-determinism.)

### Why this is a competitive advantage

- [ ] Position CPA-Bench around the **decision real firms face** — capability *per
  unit cost* on real accounting work — rather than leaderboard bragging rights. It's
  differentiated, hard to game, and directly useful to the profession the mission
  serves.

**Deliverable (when pursued):** an efficiency-aware results view — the cost–quality
frontier plus per-task cost/step instrumentation — layered onto Phase 5 reporting.

---

## Versioning & milestones

| Version | Definition of done |
|---|---|
| **v0.0** *(shipped)* | Repo + v0 harness: single-credential runner, four scorers, LLM judge, crash-safe outputs, cost-aware leaderboard, `--dry-run`/`--limit`, offline tests. |
| **v0.1** | Harness + **~50–150 expert-reviewed tasks** across the role layers (Phase 1) + a **published judge-agreement number** (Phase 3). The first honest, defensible release. |
| **v0.2** | **FinanceBench subset incorporated** under correct attribution/license (Phase 2) + **first frontier/open model panel** published with methodology (Phase 5). |
| **v0.3** | **Journal-entry canonicalization + multi-answer/structured-output scoring** (Phase 4); judge re-validated against the expanded set. |
| **v0.4+** | **Agentic / long-horizon layer** with tool use and trajectory scoring (Phase 6); ongoing dataset growth and external validation. |

Phases 1 and 3 are the critical path to v0.1 and should run in parallel as soon as there
are enough reviewed tasks to sample for judge validation.

---

## Contributing

CPA-Bench is modular and role-based on purpose: the profession is broad, and no one
person knows every corner of it. If you know bookkeeping, close, controllership, or
audit, you can contribute the tasks you know best.

- **The task schema is the contract.** A contribution is a set of valid `Task` records
  ([`cpa_bench/schema.py`](cpa_bench/schema.py)) plus a gold answer and gold rationale —
  reviewed by a credentialed accountant.
- **Stay in your lane, by role.** Tasks are tagged by `accounting_role` and `complexity`,
  so specialists can add to one layer without touching the harness.
- **Prove it offline first.** Run `--dry-run` and the offline tests
  ([`tests/test_pipeline.py`](tests/test_pipeline.py)) before opening a PR; only spend
  tokens once the plumbing is green.
- **No confidential data, ever.** Synthetic or anonymized only.

A full `CONTRIBUTING.md` and the per-role authoring guide land in Phase 1.

---

## Risks & open questions

- **Judge reliability.** The biggest risk. An unvalidated judge makes `llm_judge` scores
  unfalsifiable. Phase 3 exists to confront this, and the agreement number is published so
  readers can weigh it. Judge bias may vary by role/standard — we slice and report it.
- **Multiple correct answers.** Real accounting often admits more than one defensible
  treatment. Single-string golds will mis-grade these; Phase 4's multi-answer/partial-credit
  policy is a partial fix, not a solved problem.
- **Data licensing.** FinanceBench is CC BY-NC, not MIT. Mixing it with CPA-Bench-original
  tasks under different terms requires care; the subsets stay clearly delineated.
- **Gold-label quality.** Expert review is the safeguard, but reviewers can disagree or err.
  We record provenance, prefer multiple reviewers on judgment-heavy tasks, and treat the
  dataset as correctable rather than final.
- **Construct validity.** Does benchmark accuracy actually predict usefulness on real
  accounting work? We keep tasks grounded in genuine workflows and stay honest that a high
  score is necessary, not sufficient, for trust.
