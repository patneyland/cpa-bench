# CPA-Bench leaderboard - run-001, rescored

Rescore of `results/run-001` with the graders fixed in 612f394. The model
outputs are byte-identical to the original run; only the grading changed,
which isolates the grader fix from model nondeterminism.

Accuracy is over *scored* attempts. An empty completion from the provider is
an infrastructure error and is excluded from the denominator rather than
counted as a wrong answer.

| Model | Accuracy | Correct/Scored | Errors | Cost (USD) | $/correct |
|---|---|---|---|---|---|
| openai/gpt-5 | 100.0% | 32/32 | 0 | $0.1267 | $0.0040 |
| anthropic/claude-opus-4.5 | 96.9% | 31/32 | 0 | $0.2648 | $0.0085 |
| google/gemini-2.5-pro | 100.0% | 31/31 | 1 | $0.3646 | $0.0118 |

## By role

| Role | Correct/Scored |
|---|---|
| bookkeeper | 23/24 |
| staff_accountant | 24/24 |
| controller | 24/24 |
| auditor | 23/23 |

## What changed, and what did not

Across all three models: **94/95 correct, zero accounting errors**, one infrastructure error.

The original run reported four misses. None was an accounting mistake:

- `bk_owner_drawing_classify` accounted for three of them. All three models
  named the account correctly; the grader rejected them on phrasing, and
  rejected GPT-5 on a typographic apostrophe alone.
- `aud_variance_materiality_decision` (Gemini) returned 387 output tokens
  and empty content. That is a provider failure, not a wrong answer.

One miss survives on purpose. Opus answered `Owner's Drawing (or Withdrawals
or Pine, Drawing)` to a task that asked for the account name only. That is an
instruction-following failure and it is left failing: stripping parentheticals
would let `Cash (or Owner's Drawing)` score correct.

## Read this before citing the numbers

- **Gold answers are AI-authored and unreviewed.** No CPA has signed off on
  these 32 tasks. Until that happens these numbers are not publishable.
- **The four `llm_judge` verdicts were carried over**, not re-judged.
- **One trial per task.** No variance estimate. Fine for single-shot, not
  sufficient for anything agentic.
- **The tasks are textbook-shaped** and almost certainly appear in training
  data. This measures recall of standard treatments, not accounting judgment.

The durable finding here is the cost spread: GPT-5 answered everything
correctly at roughly a third of Gemini's cost per correct answer and half of
Opus's. At this difficulty, accuracy no longer separates the models and price
does.
