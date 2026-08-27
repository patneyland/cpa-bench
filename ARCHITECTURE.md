# CPA-Bench Architecture

Working document. Records where the project stands, what has been decided and
why, and what is still open. Written 2026-08-26, after the first real run and
the decisions that followed from it.

[`PLAN.md`](PLAN.md) predates this and has not yet been rewritten around it.
Where the two disagree, this document is current.

---

## Where things stand

**Built and working.** The v0 harness runs end to end: single-credential
runner through OpenRouter, four scorers, an LLM judge, crash-safe per-call
output, a cost-aware leaderboard, `--dry-run` and `--limit`, and 13 offline
tests. A new user can clone, install, set one key, and run.

**The first real run is done, and it changed the plan.** Three frontier
models against the 32 text tasks produced 94 of 95 scored attempts correct
and **zero accounting errors**
([`results/run-001-rescored/`](results/run-001-rescored/leaderboard.md)).

The run originally reported 96.9% / 96.9% / 93.8% with four misses. On
inspection none of the four was an accounting mistake. Three were one task
where every model named the account correctly and the grader rejected them on
phrasing, including one rejected for a typographic apostrophe. The fourth was
a provider returning empty content, scored as a wrong answer. Both graders
were fixed (`612f394`) and the run rescored against byte-identical model
output.

Two conclusions follow.

*The text set is saturated.* Three frontier systems separated by a single
formatting slip is not a measurement. It cannot rank models and adding more
questions of the same kind will not change that.

*Cost is the only axis left with variance.* GPT-5 answered everything
correctly at $0.0040 per correct answer against Gemini's $0.0118 and Opus's
$0.0085. When accuracy stops discriminating, price is the entire decision.

**Not publishable yet.** The gold answers are AI-authored and no CPA has
reviewed them. That review gates everything downstream.

---

## The architecture this is moving to

### The shape

```
task folder  -->  workspace copy  -->  PROGRAM  -->  artifact  -->  GRADER  -->  record
                  (scratch, mutable)   (+ model)     (a file)      (deterministic)
```

A task is a folder. A program is anything that reads the folder and writes a
file. A grader checks the file. A record names the program and the model
separately.

### The four objects

**Task.** A directory holding `instruction.md`, `seed/` (whatever would be on
the desk: a transaction export, a chart of accounts, prior-period coding, a
bank statement, an email thread), `expected/`, `grade.py`, and `task.toml`
for timeouts and network posture. Labels for slicing results:
`accounting_role`, `complexity`, `accounting_standard`, `family`. Provenance:
`author`, `reviewer`, `reviewed_on`, `license`, `source`, `version`. Nothing
in a task knows anything about programs.

**Program.** A platform plus its configuration, frozen and versioned. The
model is a parameter handed to it, never part of its identity. Four to start:

| program | job |
|---|---|
| `plain_loop_v1` | ~20 lines, frozen forever. The only row models without tool use can run, so it carries any claim about capability over time. Also the hedge if a third-party CLI changes behavior. |
| `opencode@<pin>` | Primary. Model-agnostic by design, so every provider competes on identical footing. Reads `.claude/skills/*/SKILL.md`, so skills drop in unmodified. |
| `claude_code@<pin>` | What firms actually use. External validity. |
| `claude_code@<pin>+skill` | The same, with a skill installed. The difference between these two rows is what a written skill is worth. |

**Grader.** Reads the workspace after the program exits. Deterministic where
possible: diff the output CSV, diff the trial balance, check the
reconciliation ties. An unparseable artifact scores *unscored*, not zero, on
the grounds that a malformed output and a wrong answer are different
failures and averaging them together destroys information.

**Record.** `task-set version + program + program version + model + effort +
accuracy with CI over 5 trials + cost + tokens + date`. Never a bare model
name.

### Why programs are a first-class dimension

Published 2026 work measures harness-induced variance at several times
model-induced variance. One controlled factorial found a 7.8x ratio with six
of nine model-pair rankings reversing across harnesses. MLE-bench's own
cross-product had GPT-4o at 8.7% under one scaffold and 0.8% under another.

A leaderboard row that says only "GPT-5 scored X" is therefore not a
measurement, because most of X came from something the row does not name.
Every row here carries the program.

The corollary is that the grid reads two ways. Hold the program fixed and
vary the model, and you are comparing models. Hold the model fixed and vary
the program, and you are measuring what scaffolding is worth. Both are real
findings and one grid produces both. What you may never do is compare a cell
in one row against a cell in another and call it a model result.

### Task families are a label, not a fork

Every task runs through the same path and writes to the same workspace,
including today's multiple-choice items, which write `answer.txt`. There is
no branch in the runner for "agentic" versus "text." A single-shot program
returns a string and the harness writes it to the workspace on its behalf, so
graders always have one input shape.

`family` therefore slices the results table and nothing more. Any task type
can be added.

The one rule that survives: never average across families. A thirty-second
multiple-choice item and a forty-minute reconciliation do not belong in one
number. Aggregating heterogeneous tasks is provably not neutral, so the
per-family table is the authoritative artifact and any blended score is a
convenience index sitting on top of it.

---

## Decisions made, and why

**OpenCode is the primary program.** It is model-agnostic, so the same
program runs GPT-5, Opus, DeepSeek, and Qwen with a string change and no
translating proxy. It is open source, so a version can be pinned and
inspected. It has first-party skill support and reads `.claude/skills/`, so
existing skills need no porting. `opencode run --format json --auto` is a
clean headless contract, and `--attach` against a running `opencode serve`
avoids paying cold-boot cost on every one of several hundred runs.

**Own runner, built to be Inspect-portable.** UK AISI's Inspect is where
METR and Apollo both landed, and its ~150 evals contain nothing for
accounting or finance. But with OpenCode primary, an entrant is a subprocess
against a folder, which makes the runner small and weakens the case for
adopting a framework now. The port stays cheap as long as four rules hold:

1. Tasks are data on disk, never Python. Understanding a task must never
   require importing this codebase.
2. Graders are pure: `grade(task, workspace_path) -> Score`. No importing the
   runner, no reading config objects, no computing where the workspace is.
   Break this one and the port becomes a rewrite.
3. Programs are subprocess calls: `run(workspace_path, model) -> usage`.
4. Records are written by one separate function, never inline in the loop.

Precedent: METR moved an entire pre-existing task standard onto Inspect with
a single bridge file of roughly 40 lines.

**The text set freezes at 32.** Zero accounting errors in 96 attempts means
more textbook items will not discriminate between anything. This overrules
PLAN Phase 1's target of 50 to 150 tasks.

Adversarial filtering for a harder text tier (the MMLU to MMLU-Pro playbook)
was considered and rejected. Real accounting is hard because of mess,
ambiguity and missing documents, not because a question is tricky. A hard
text tier would manufacture artificial difficulty. The mess belongs in folder
tasks, where it is genuine.

Freeze means the count stops growing, not that quality is final. CPA review
is the last change the file gets, after which it is stamped
`cpa-bench-text-v1` with a content hash and every published result names that
version.

**run-001 gets published as a closed result**, after CPA review. The claim:
on 32 textbook-level tasks spanning bookkeeper to auditor, three frontier
models made zero accounting errors across 96 attempts, at a 3x spread in cost
per correct answer. Published with its bound, that these are textbook-shaped
tasks almost certainly present in training data, so it measures recall of
standard treatments rather than accounting judgment.

**Score final artifacts only, for now.** Whether a model asks instead of
silently guessing on genuinely ambiguous input is the most interesting thing
on the table and it is deferred. Adding it later costs nothing structurally,
because it is just another grader reading the workspace. The cheap version,
when it comes, is to plant unresolvable rows in the seed data and check
whether the output flags them, with no simulated user needed.

---

## Still open

- **Whether `docs/` (the thesis worksheet) belongs in the public repo.** It
  is untracked and unanswered.
- **PLAN.md needs rewriting** around all of the above. The README already
  promises this.
- **Contributor readiness.** `Task.from_dict` rejects unknown fields, which
  is deliberate strictness with an unwanted side effect; a `metadata`
  passthrough fixes it in one line. There are no provenance fields, no
  `CONTRIBUTING.md`, no authoring guide, and no task-id namespacing, so two
  contributors would collide silently. Roughly two hours of work, and it is
  what stands between this and accepting outside tasks.
- **Cost metering for programs that do not self-report.** A metering proxy
  in front of the model API measures usage at the HTTP boundary and works for
  any entrant, including binaries nobody wrote here. Needed once agentic runs
  start costing real money.
- **Trajectory audit.** An open program axis invites reward hacking, and in
  accounting the hacks are obvious: plugging a difference, reading the
  expected file, hardcoding an answer. Needed the day an outside submission
  is accepted, not before.

## Critical path

**CPA review of the 32 gold answers.** It gates the freeze, gates
publication, and gates anyone citing this. It is a few hours of one
credentialed accountant's time, and it is the only blocker that cannot be
cleared by writing code.

Then: the schema and contributor work, then the first folder task
(Upwork transaction export to a QuickBooks import file, where a reference
implementation already exists and can generate the expected output, making
grading free).
