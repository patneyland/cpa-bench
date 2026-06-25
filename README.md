# CPA-Bench

**An open benchmark for measuring how well AI performs the real work of accounting — so accountants can prepare for AI instead of hiding from it.**

CPA-Bench extends [FinanceBench](https://github.com/patronus-ai/financebench) beyond open-book financial QA into the procedural, judgment-heavy, role-based work that accountants actually do: bookkeeping, period-end close, adjustments, reconciliations, GAAP/IFRS application, and audit-style reasoning.

> **Status:** `v0.0` — pre-release. We are at the very beginning: defining the mission, the schema, and the first tasks. The repository structure, dataset, and evaluation harness are being built in the open. Nothing here is final, and contributions, critique, and collaboration are welcome.

---

## Mission

To give the accounting profession an honest, public, and continually updated map of what AI can and cannot do across real accounting workflows — and to use that map to help accountants become *more* capable, not less relevant.

A benchmark is the vehicle. The destination is a profession that meets AI with clear eyes: knowing where these tools are already trustworthy, where they fail, where a human must stay in the loop, and what skills are worth building now.

---

## Motivation

I am an accounting PhD student, and I believe the profession is at a hinge moment.

When earlier technological waves arrived, accounting — both the practice and the academy — too often met them late and defensively. We risk doing it again with AI: treating it as a threat to be managed, a compliance problem, or something to quietly wait out. That posture leaves accountants unprepared, and an unprepared profession is one that gets *done to* rather than one that shapes its own future.

I want the opposite. **I don't want accountants to be caught flat-footed by AI. I want them to lead with it.**

I believe AI can make accountants genuinely better — and the job genuinely more enjoyable — by taking on the mechanical and freeing people for the parts of the work that require judgment, skepticism, communication, and ethics. More than that, I believe AI can advance the things accounting exists to do in the first place:

- **Inform investors** with clearer, faster, more complete information.
- **Help people and organizations make better financial decisions.**
- **Create transparency and accountability** — the entire reason the profession holds public trust.

Every one of those goals can be *improved* with AI, not eroded by it. But that only happens if we look directly at the technology and measure it honestly — its strengths *and* its failure modes — instead of looking away.

So the purpose of CPA-Bench is twofold:

1. **Increase transparency.** Make the real capabilities and limits of AI on accounting work visible, measurable, and public — so claims (in either direction: hype or fear) can be checked against evidence.
2. **Inspire preparation.** Show accountants, students, educators, and firms concretely *how* AI fits into their workflows, where it helps, where it must be supervised, and how to build the skills to work alongside it.

This is an optimistic project with a demanding standard: optimism about what the profession can become, paired with rigor about what the tools can actually do today.

---

## What CPA-Bench measures

FinanceBench answers questions *from* financial statements. CPA-Bench asks whether AI can do the work that *produces and audits* those statements — across the roles a real accounting function contains.

| Layer | Example tasks | Role lens |
|---|---|---|
| **Foundational** (from FinanceBench) | Statement analysis, ratios, metric extraction | Analyst |
| **Bookkeeping** | Classify transactions, generate double-entry journal entries, post to the ledger | Bookkeeper |
| **Period-End Close** | Accruals, deferrals, depreciation, trial balance → financial statements | Staff Accountant |
| **Compliance & Judgment** | GAAP/IFRS application, revenue recognition (ASC 606), error and fraud-indicator detection | Controller |
| **Multi-Step / Agentic** | Process transaction batches over months, bank and intercompany reconciliation, consolidation | Controller / Auditor |
| **Assurance** | Sampling, risk assessment, variance and analytical review | Auditor |

Each task is designed to test not just *can the model get the number*, but *can it reason through the procedure, apply the right standard, and show its work the way a trustworthy professional would.*

---

## Why a benchmark, specifically

- **It makes the conversation evidence-based.** "AI can/can't do accounting" becomes a measurable claim instead of a vibe.
- **It's a curriculum signal.** Where models reliably succeed and reliably fail tells students and firms where to invest human skill.
- **It's a transparency instrument.** Public tasks, public methodology, public results — the same values accounting asks of the companies it reports on.
- **It's extensible.** The profession is broad; a modular, role-based design lets practitioners and academics contribute the tasks they know best.

---

## Running the benchmark (v0 harness)

The evaluation harness lives in [`cpa_bench/`](cpa_bench/). You give it a list of
models and a set of tasks, and it runs and scores them — reaching **every model,
and the grader, through a single OpenRouter credential**. Each task is
self-describing: it carries how it should be graded (`eval_method`), so the
runner stays simple.

```bash
pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-...        # the only credential you need
```

**Testing protocol — built in, so you never fire a full run just to check plumbing:**

```bash
# 1. Full pipeline offline — no network, no key, no cost. Exercises the
#    runner, every scorer, and the leaderboard via a mock client.
python -m cpa_bench.cli run --tasks data/sample_tasks.jsonl --dry-run

# 2. Cheap real smoke test — first 2 tasks against the real models/judge.
python -m cpa_bench.cli run --tasks data/sample_tasks.jsonl --limit 2

# 3. Full run.
python -m cpa_bench.cli run --models configs/models.yaml \
    --tasks data/sample_tasks.jsonl --out results/run-001

# Offline unit tests (scorers + end-to-end):
python tests/test_pipeline.py        # or: python -m pytest -q
```

Outputs land in the `--out` directory: `raw/<model>/<task>.json` (one record per
call, so a crash loses nothing), `scores.jsonl`, and a `leaderboard.md` with
accuracy and **real per-model cost** (OpenRouter reports usage cost per call).

Configure the run in [`configs/models.yaml`](configs/models.yaml) — just the
model list, the judge, and concurrency. Sample tasks in
[`data/sample_tasks.jsonl`](data/sample_tasks.jsonl) already cover four grading
methods (`numeric`, `exact`, `mcq`, `llm_judge`) across four accounting roles.

**Roughly what a run costs.** Cost is dominated by how much context each task
carries. Against the FinanceBench 150-question subset with the gold *evidence
excerpt* supplied (~1.4K tokens of context each), a full run on an Opus-tier
model (~$5/$25 per 1M input/output tokens) is on the order of **a few dollars**.
Feeding entire source filings instead (long-context mode, ~100K tokens each)
pushes the same run toward **$50–150**. Start with the cheap evidence mode while
building the harness; the `--dry-run` and `--limit` modes above keep iteration
free or near-free.

**Validating the judge.** Open-ended (`llm_judge`) scores are only as trustworthy
as the judge behind them, so the harness can grade the judge against human labels:

```bash
# Score the deployed judge on a labeled set -> agreement, Cohen's kappa,
# confusion matrix, and the false-pass rate (how often it accepts a wrong answer).
python -m cpa_bench.cli judge-eval --items data/judge_eval_seed.jsonl --out results/judge

# Build a labeling template from a real run, for a CPA to mark correct/incorrect:
python -m cpa_bench.cli judge-prep --run results/run-001/scores.jsonl \
    --tasks data/cpa_bench_v0_1.jsonl --out data/judge_eval_to_label.jsonl
```

The seed set ([`data/judge_eval_seed.jsonl`](data/judge_eval_seed.jsonl)) is synthetic
(answers whose correctness we know, including *subtly* wrong ones) so you can run it
today; the real validation set is CPA-labeled real model answers (PLAN Phase 3). The
metric that matters most is **false-pass** — a judge that rubber-stamps wrong answers
silently inflates the leaderboard, so it's reported first.

## Roadmap (high level)

Detailed planning lives in [`PLAN.md`](PLAN.md). In brief:

1. **Setup & replication** — establish repo structure; bring in the FinanceBench open subset as a foundation and attribute it properly.
2. **Accounting-specific dataset** — extend the schema (role, complexity, required reasoning, expected outputs) and build the first 100–300 expert-reviewed tasks across the layers above.
3. **Evaluation framework** — exact-match on numbers/entries, rubric- and LLM-judge scoring, and an agentic mode with tool use (calculation, ledger queries).
4. **Baselines & publication** — run frontier and open models; publish results and methodology.
5. **Launch & iteration** — open contribution, external validation by practicing accountants and academics, and expansion toward long-horizon, multi-period tasks.

---

## Attribution

CPA-Bench builds directly on **FinanceBench** by Patronus AI. We gratefully acknowledge that work as the foundation this project extends. FinanceBench citation and licensing details will be reproduced here as the dataset is incorporated, and CPA-Bench will comply with the terms of any upstream data it uses.

> Islam et al., *FinanceBench: A New Benchmark for Financial Question Answering.* Patronus AI. https://github.com/patronus-ai/financebench

*(Full BibTeX and license notes to be added in `ATTRIBUTION.md`.)*

---

## License

To be finalized. The intent is a permissive license for original code, with dataset licensing chosen to (a) respect upstream FinanceBench terms and (b) keep CPA-Bench as open and useful to the profession as possible. See `LICENSE` *(coming)*.

---

## Disclaimer

CPA-Bench is a research benchmark. It does **not** provide accounting, audit, tax, or investment advice, and model outputs measured here should not be relied on for real financial reporting. All data is intended to be public or synthetic; no confidential or sensitive client information belongs in this repository.

---

## Get involved

This project is being built in the open by someone who believes the accounting profession's best response to AI is to engage it directly, measure it honestly, and prepare deliberately. If you are an accountant, auditor, educator, student, or researcher and that resonates — contribution guidelines are on the way, and your expertise is wanted.
