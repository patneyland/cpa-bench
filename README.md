# CPA-Bench

**How good is AI at accounting?**

CPA-Bench is an open benchmark that tries to answer that with evidence instead of assertion: a growing set of accounting tasks, an environment to do the work in, and a known-correct answer to grade against.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen)
![Status](https://img.shields.io/badge/status-pre--release%20v0.x-orange)

---

## Why this exists

From my own experience, some accountants are frightened of what AI can do. The worry runs from "this changes my job" down to "I will not have one." Also from my own experience, business owners look at the same technology and want to fire their accountant, because they have seen enough to believe the software will do it. I cannot tell you either group is the majority. I can tell you neither one is small.

Meanwhile thousands of startups and established software companies are working to make both of those futures real, selling capacity to firms that want more output without more headcount, and selling replacement to businesses that want the line item gone.

So: are these groups crazy, or is there truth in what they think, and if there is, how much?

There is truth in it. AI can do accounting, and on a good deal of it, it is already as good as a professional. That part is no longer the interesting question.

The interesting question is the map. Which parts of the work is it reliable at, which parts does it fail at, how is it moving on each of them over time, and what does each one cost in time and tokens. Almost any knowledge task can be automated if you break it into small enough pieces and supply enough examples and instruction. Plenty of tasks are not worth that effort. Knowing which is which is what the profession actually needs, and nobody is publishing it.

That map is what CPA-Bench is for. It should let an accountant see where AI can be trusted to carry work and where a human has to stay in the loop, let a firm see what a given piece of automation costs before committing to it, and give researchers an instrument for questions nobody has been able to ask yet.

## What it has found so far

The first real run, three frontier models against 32 textbook-level tasks spanning bookkeeping through audit ([`results/run-001-rescored/`](results/run-001-rescored/leaderboard.md)):

| Model | Accuracy | Correct/Scored | Errors | Cost (USD) | $/correct |
|---|---|---|---|---|---|
| openai/gpt-5 | 100.0% | 32/32 | 0 | $0.1267 | $0.0040 |
| anthropic/claude-opus-4.5 | 96.9% | 31/32 | 0 | $0.2648 | $0.0085 |
| google/gemini-2.5-pro | 100.0% | 31/31 | 1 | $0.3646 | $0.0118 |

**94 of 95 scored attempts correct, and zero accounting errors.** The single miss is a model answering `Owner's Drawing (or Withdrawals or Pine, Drawing)` to a task that asked for the account name only, which is a formatting failure. The one error is a provider returning empty content.

Two things follow, and the second matters more.

At this level the work is solved, so this task set cannot rank models any more. Three frontier systems separated by one formatting slip is not a measurement. Read it as a floor: on standard treatments with the facts already laid out, current models do not make accounting mistakes.

What still separates them is price. GPT-5 answered everything correctly at roughly a third of Gemini's cost per correct answer and half of Opus's. Once accuracy stops discriminating, cost is the whole decision, and it is the number a firm actually needs.

**These numbers are not yet publishable.** No CPA has reviewed the gold answers. See [Caveats](#caveats-and-limitations).

## What it measures

[`data/cpa_bench_v0_1.jsonl`](data/cpa_bench_v0_1.jsonl) holds 32 tasks split evenly across four accounting roles, 8 each:

| Role | Complexity tier | Example tasks |
|---|---|---|
| **Bookkeeper** | foundational | double-entry journal entries, ledger posting, transaction classification, normal balances |
| **Staff accountant** | period_close | prepaid and accrual deferrals, straight-line depreciation, accrued interest and wages, multi-step net-income adjustment |
| **Controller** | compliance | FIFO/LIFO/weighted-average cost flow, ASC 606 revenue timing, ASC 842 lease classification, capitalize-vs-expense judgment |
| **Auditor** | assurance | misstatement projection, analytical and variance review, DSO, assertion identification, fraud red-flag and inherent-risk judgment |

Each task carries the grading method it should be scored with, so the runner stays simple and dispatches to the right scorer:

- **`numeric`** (18 tasks): parses the model's number with accounting-aware handling (dollar signs, parentheses-as-negative, percentages, comma separators) and compares against gold within a relative tolerance, default 1%.
- **`mcq`** (8 tasks): matches the chosen letter, tolerating `b` vs `b) ...` formatting.
- **`exact`** (2 tasks): normalized string match, folding typographic punctuation to ASCII and accepting the alternative account names a task declares. An account has several correct written forms, and a grader that rejects one of them is measuring itself.
- **`llm_judge`** (4 tasks): a strong model grades open-ended judgment answers against the gold answer and a gold rationale.

## How it works

```
tasks (.jsonl, self-describing)
        |
        v
   runner  ---->  model client (OpenRouter, one credential reaches every model)
        |                |
        |            raw output  ---->  FINAL ANSWER: extraction
        v
   scorer dispatch by eval_method
        |
     numeric | exact | mcq | llm_judge ----> judge model
        |
        v
  leaderboard.md (accuracy + real per-model cost)  +  scores.jsonl  +  raw/<model>/<task>.json
```

Every model and the judge are reached through a single `OPENROUTER_API_KEY`. The runner writes one JSON record per call before aggregating, so a crash loses nothing. Cost comes from OpenRouter's reported per-call usage and is rolled up per model, which makes the leaderboard a cost-versus-quality view rather than accuracy alone.

An empty completion from a provider is recorded as an error, not a wrong answer. A model that never got the chance to respond has not failed the accounting.

## Judge validation

Open-ended scores are only as trustworthy as the judge behind them, so CPA-Bench grades its own judge. The validation harness ([`cpa_bench/judge_eval.py`](cpa_bench/judge_eval.py)) runs the *same* judge the benchmark ships against a labeled set and reports agreement, Cohen's kappa, a confusion matrix, and false-pass and false-fail rates sliced by role and complexity.

False-pass is reported first because it is the dangerous error: a judge that rubber-stamps wrong answers makes every model look better than it is.

The seed set ([`data/judge_eval_seed.jsonl`](data/judge_eval_seed.jsonl)) is 12 synthetic items so the pipeline runs today. The real validation set will be CPA-labeled model answers, produced via the `judge-prep` command below.

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit OPENROUTER_API_KEY=sk-or-...
```

```bash
# Full pipeline offline: no network, no key, no cost.
python -m cpa_bench.cli run --tasks data/cpa_bench_v0_1.jsonl --dry-run

# Cheap real smoke test: first 2 tasks against the real models and judge.
python -m cpa_bench.cli run --tasks data/cpa_bench_v0_1.jsonl --limit 2

# Full run.
python -m cpa_bench.cli run --models configs/models.yaml \
    --tasks data/cpa_bench_v0_1.jsonl --out results/run-002
```

Validate the judge, and build a CPA labeling template from a real run:

```bash
python -m cpa_bench.cli judge-eval --items data/judge_eval_seed.jsonl --out results/judge

python -m cpa_bench.cli judge-prep --run results/run-001/scores.jsonl \
    --tasks data/cpa_bench_v0_1.jsonl --out data/judge_eval_to_label.jsonl
```

Offline tests (no key, no network): `python -m pytest -q`

## Where this goes next

The text task set above is finished work. Once a CPA has reviewed the golds it freezes as `cpa-bench-text-v1` and stops growing, because more questions of the same kind will not tell anyone anything new. Its lasting job is narrow and worth having: it is the only set that models without tool use can attempt, so it is what charts capability backward through time.

The next form of the benchmark is closer to the actual job. A task becomes a folder holding what would be on your desk (a transaction export, a chart of accounts, prior-period coding, a bank statement, an email thread), the instruction says what to produce, and grading checks the artifact that comes out. Did the trial balance come out right. Does the reconciliation tie. Is the import file valid.

Three consequences of building it that way:

**Any system can enter.** The contract is a folder in and a file out, so a bare model with a file-writing loop, a terminal agent like OpenCode or Claude Code, or something nobody has written yet all attempt the same task and are graded by the same check. No integration work per entrant.

**Correctness stops depending on phrasing.** Checking the books instead of the sentence removes most of the multiple-defensible-answers problem that makes single-string grading unfair to real accounting.

**Every result names the system, not just the model.** Published work now puts harness-driven variance at several times model-driven variance, with the same model swinging ten points or more across scaffolds. A row that says only "GPT-5 scored X" is not a measurement. Rows here carry the program, its version, the model, and the cost.

Also planned: FinanceBench's open subset folded in as the analyst layer under its CC BY-NC terms, a published judge-agreement number from CPA labels, and a cost-quality frontier rather than a single-axis ranking.

Detailed planning lives in [`PLAN.md`](PLAN.md), which predates the results above and is being rewritten around them.

## Caveats and limitations

This is an early project built in the open. Please do not treat it as a validated benchmark yet.

- **Gold answers are AI-authored and not expert-reviewed.** The `v0.1` set was drafted by AI and arithmetic-checked, but no CPA has signed off. Some items turn on genuine professional judgment (lease classification, ASC 606 timing, audit-risk calls) where a wrong gold would corrupt the score. This is the gate on everything else. Treat the set as a draft to be reviewed, not an answer key.
- **The tasks are textbook-shaped.** They look like intermediate accounting exercises, which means models have very likely seen thousands of their kind in training. The honest reading of a perfect score is that frontier models do not miss standard treatments when the facts are laid out for them. That is narrower than "AI can do accounting."
- **One trial per task.** No variance estimate. Acceptable for single-shot text answers, not sufficient for anything agentic, where repeated trials with error bars are the minimum.
- **The judge-validation labels are synthetic.** The published human-versus-judge agreement number that would make `llm_judge` scores trustworthy does not exist yet.
- **The leaderboard is a lower bound.** It reports what the submitted systems achieved. A skilled practitioner will always get more out of these models than a benchmark harness does, so the claim is never "AI cannot do this," only "no submitted system has done this yet."
- **FinanceBench is not yet incorporated.** It is the intended foundation and will be added only with proper attribution under its CC BY-NC terms.

## Disclaimer

CPA-Bench is a research benchmark. It does not provide accounting, audit, tax, or investment advice, and model outputs measured here should not be relied on for real financial reporting. All data is public or synthetic; no confidential client information belongs in this repository.

## Attribution

CPA-Bench builds on **FinanceBench** by Patronus AI, gratefully acknowledged as the foundation this project extends. Full citation and license notes will be reproduced as the dataset is incorporated.

> Islam et al., *FinanceBench: A New Benchmark for Financial Question Answering.* Patronus AI. https://github.com/patronus-ai/financebench

## Author

Built by Patrick Neyland, an accounting PhD-track academic working in applied AI. [Neyland Solutions](https://neylandsolutions.com).

Contributions, critique, and gold-answer review are exactly what this project needs.
