# CPA-Bench

**An open benchmark measuring how well AI does the real work of accounting, so accountants can prepare for AI instead of avoiding it.**

CPA-Bench extends [FinanceBench](https://github.com/patronus-ai/financebench) beyond open-book financial QA into the procedural, judgment-heavy work an accounting function actually performs: bookkeeping, period-end close, GAAP/IFRS application, revenue recognition, and audit-style reasoning. It grades models on those tasks, tracks what each run costs, and (the part most benchmarks skip) measures whether the AI grader can be trusted in the first place.

> **Status: `v0.x`, pre-release.** The evaluation harness is built and tested end to end. There is no published real-model run yet, and the task gold answers have not been reviewed by a CPA. This is honest scaffolding, not a finished benchmark. Contributions, critique, and gold-answer review are exactly what the project needs.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen)
![Status](https://img.shields.io/badge/status-pre--release%20v0.x-orange)

---

## Why this exists

The accounting profession is deciding right now how to meet AI, and the easy posture is avoidance: treat it as a compliance headache or wait it out. That leaves accountants unprepared for tools that are already entering their workflows. The honest alternative is to look directly at what these models can and cannot do on real accounting work, and to measure it in public so claims (hype or fear) can be checked against evidence. CPA-Bench is that measuring instrument: a public, role-based map of where AI is already reliable, where it fails, and where a human has to stay in the loop.

## What it measures

The current task set, [`data/cpa_bench_v0_1.jsonl`](data/cpa_bench_v0_1.jsonl), holds **32 tasks split evenly across four accounting roles, 8 tasks each**:

| Role | Complexity tier | Example tasks |
|---|---|---|
| **Bookkeeper** | foundational | double-entry journal entries, ledger posting, transaction classification, normal balances |
| **Staff accountant** | period_close | prepaid/accrual deferrals, straight-line depreciation, accrued interest and wages, multi-step net-income adjustment |
| **Controller** | compliance | FIFO/LIFO/weighted-average cost flow, ASC 606 revenue timing, ASC 842 lease classification, capitalize-vs-expense judgment |
| **Auditor** | assurance | misstatement projection, analytical/variance review, DSO, assertion identification, fraud red-flag and inherent-risk judgment |

A small four-task sample set ([`data/sample_tasks.jsonl`](data/sample_tasks.jsonl)) adds an `analyst` role and exists to exercise the harness.

Each task is self-describing: it carries the grading method it should be scored with, so the runner stays simple and dispatches to the right scorer. Four scorers exist:

- **`numeric`** (18 of the 32 tasks): parses the model's number with accounting-aware handling (dollar signs, parentheses-as-negative, percentages, comma separators) and compares against gold within a relative tolerance, default 1%.
- **`mcq`** (8 tasks): matches the chosen letter, tolerating `b` vs `b) ...` formatting.
- **`exact`** (2 tasks): normalized string match (case, whitespace, trailing period).
- **`llm_judge`** (4 tasks): a strong model grades open-ended judgment answers against the gold answer and a gold rationale.

## How it works

```
tasks (.jsonl, self-describing)
        |
        v
   runner  ──>  model client (OpenRouter, one credential reaches every model)
        |              |
        |          raw output  ──>  FINAL ANSWER: extraction
        v
   scorer dispatch by eval_method
        |
   ┌────┴───────────────┬──────────┬───────────────┐
 numeric              exact       mcq           llm_judge ──> judge model
 (tolerance,                                                  (same credential)
  parens-as-neg)
        |
        v
  leaderboard.md  (accuracy + real per-model cost in USD)  +  scores.jsonl  +  raw/<model>/<task>.json
```

Every model and the judge are reached through a single `OPENROUTER_API_KEY`. The runner writes one JSON record per call before aggregating, so a crash loses nothing. Cost is read from OpenRouter's reported per-call usage and rolled up per model, which makes the leaderboard a cost-vs-quality view rather than accuracy alone.

## Judge validation

Open-ended scores are only as trustworthy as the judge behind them, so CPA-Bench grades its own judge. The validation harness ([`cpa_bench/judge_eval.py`](cpa_bench/judge_eval.py)) runs the *same* judge the benchmark ships against a labeled set and reports:

- **Agreement** with the human labels.
- **Cohen's kappa**, agreement corrected for chance.
- A **confusion matrix**.
- **False-pass rate** (the judge accepted a wrong answer, which silently inflates the leaderboard) and **false-fail rate**, sliced by accounting role and complexity.

False-pass is reported first because it is the dangerous error: a judge that rubber-stamps wrong answers makes every model look better than it is. A benchmark that publishes its judge's reliability is more trustworthy than one that asks you to assume it, and re-validation is expected whenever the judge model or prompt changes.

The seed set ([`data/judge_eval_seed.jsonl`](data/judge_eval_seed.jsonl)) is 12 synthetic items (answers whose correctness we assigned, including subtly wrong ones) so the pipeline runs today. The real validation set will be CPA-labeled real model answers, produced via the `judge-prep` command below.

## Quickstart

```bash
pip install -r requirements.txt

# Copy the env template and paste your key (one credential reaches every model + the judge):
cp .env.example .env        # then edit OPENROUTER_API_KEY=sk-or-...
# or: export OPENROUTER_API_KEY=sk-or-...
```

```bash
# 1. Full pipeline offline (no network, no key, no cost). Exercises the runner,
#    every scorer, and the leaderboard through a mock client.
python -m cpa_bench.cli run --tasks data/cpa_bench_v0_1.jsonl --dry-run

# 2. Cheap real smoke test: first 2 tasks against the real models and judge.
python -m cpa_bench.cli run --tasks data/cpa_bench_v0_1.jsonl --limit 2

# 3. Full run.
python -m cpa_bench.cli run --models configs/models.yaml \
    --tasks data/cpa_bench_v0_1.jsonl --out results/run-001
```

Outputs land in the `--out` directory: `raw/<model>/<task>.json` (one record per call), `scores.jsonl`, and `leaderboard.md`. Configure the model list, judge, and concurrency in [`configs/models.yaml`](configs/models.yaml).

Validate the judge, and build a CPA labeling template from a real run:

```bash
# Score the deployed judge on a labeled set -> agreement, Cohen's kappa,
# confusion matrix, false-pass / false-fail rates (sliced by role + complexity).
python -m cpa_bench.cli judge-eval --items data/judge_eval_seed.jsonl --out results/judge

# Turn a completed run into a labeling template for a CPA to mark correct/incorrect.
python -m cpa_bench.cli judge-prep --run results/run-001/scores.jsonl \
    --tasks data/cpa_bench_v0_1.jsonl --out data/judge_eval_to_label.jsonl
```

Offline tests (no key, no network):

```bash
python -m pytest -q              # or: python tests/test_pipeline.py
```

## Example output

> **Illustrative format, not real results.** No real-model panel has been run or published yet. The numbers below show what the harness emits, not measured performance.

Leaderboard (`leaderboard.md`):

| Model | Accuracy | Correct/N | Cost (USD) | Errors |
|---|---|---|---|---|
| model-a | 84.4% | 27/32 | $0.0412 | 0 |
| model-b | 78.1% | 25/32 | $0.0190 | 0 |
| model-c | 71.9% | 23/32 | $0.0061 | 0 |

Judge validation report (`judge_report.md`), shown here against the 12-item synthetic seed:

```
Agreement with humans: 100.0%   Cohen's kappa: 1.000
False-pass (accepted a wrong answer): 0  (0.0% of human-incorrect items)
False-fail (rejected a correct answer): 0  (0.0% of human-correct items)
```

That 100% / kappa 1.000 is on synthetic seed data, not a real CPA-labeled set, and should not be read as a validated trust number.

## Roadmap

Detailed planning lives in [`PLAN.md`](PLAN.md). In brief:

- **CPA-reviewed gold answers.** Replace AI-drafted golds with a 50 to 150 task set reviewed and signed off by credentialed accountants, with reviewer provenance recorded.
- **FinanceBench foundation, attributed correctly.** Fold in the FinanceBench open subset as the analyst layer under its CC BY-NC terms, with evidence-mode and long-context-mode runs.
- **A published judge-agreement number.** Build a real CPA-labeled validation set, publish judge kappa sliced by role and complexity, and set a threshold below which a task type is not judge-graded.
- **First real model panel.** Run frontier and open models, publish results and methodology sliced by role and complexity, not one aggregate score.
- **Cost-quality frontier view.** Report cost per correct answer and accuracy-per-dollar, and plot the Pareto frontier so a cheaper model that ties a pricier one is the headline.
- **Scoring robustness and an agentic layer (later).** Journal-entry canonicalization, multi-answer grading, and multi-step tasks with tool use.

## Caveats and limitations

This is an early, in-progress project built in the open. Please do not treat anything here as a validated benchmark yet.

- **Gold answers are AI-authored and not yet expert-reviewed.** The `v0.1` task set was drafted by AI and arithmetic-checked, but no CPA has signed off. Some items involve genuine professional judgment (lease classification, ASC 606 timing, audit-risk calls) where a wrong gold label would corrupt scores. Treat it as a draft to be reviewed, not an answer key.
- **The judge-validation labels are synthetic.** The seed set uses answers whose correctness we assigned, not human-labeled real model outputs. The published human-vs-judge agreement number that would make `llm_judge` scores trustworthy does not exist yet.
- **No model results have been published.** The harness runs, but no leaderboard here reflects a real, reviewed run.
- **FinanceBench is not yet incorporated.** It is the intended foundation, but its dataset is CC BY-NC and will be added only with proper attribution and licensing.

In short: the scaffolding and methodology are real and runnable; the dataset and results are not yet validated.

## Disclaimer

CPA-Bench is a research benchmark. It does not provide accounting, audit, tax, or investment advice, and model outputs measured here should not be relied on for real financial reporting. All data is intended to be public or synthetic; no confidential client information belongs in this repository.

## Attribution

CPA-Bench builds on **FinanceBench** by Patronus AI, gratefully acknowledged as the foundation this project extends. Full citation and license notes will be reproduced as the dataset is incorporated.

> Islam et al., *FinanceBench: A New Benchmark for Financial Question Answering.* Patronus AI. https://github.com/patronus-ai/financebench

## Author

Built by Patrick Neyland, an accounting PhD-track academic working in applied AI. [Neyland Solutions](https://neylandsolutions.com).
