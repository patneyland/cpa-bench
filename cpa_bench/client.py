"""Model clients.

Two implementations behind one interface:

* ``OpenRouterClient`` — real calls through OpenRouter (OpenAI-compatible).
  One key reaches every model and the judge.
* ``MockClient`` — no network, no key. Returns a canned response so the
  whole runner + scorer + reporting pipeline can be exercised offline.
  This is what powers ``--dry-run`` and the test suite: the testing
  protocol that lets you validate the harness without firing a real run.
"""

from __future__ import annotations

from dataclasses import dataclass

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    # OpenRouter returns a per-call USD cost in usage; we surface it so the
    # leaderboard can report real spend per model.
    cost_usd: float = 0.0
    error: str | None = None


class OpenRouterClient:
    """Real client. Lazily constructs the OpenAI SDK so that importing this
    module never requires the dependency or a key (keeps --dry-run light)."""

    def __init__(self, api_key: str, base_url: str = OPENROUTER_BASE_URL):
        from openai import OpenAI  # imported lazily on purpose

        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, model: str, system: str, user: str) -> Completion:
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # ask OpenRouter to include its cost accounting in usage
                extra_body={"usage": {"include": True}},
            )
        except Exception as exc:  # noqa: BLE001 - surface any provider error per-call
            return Completion(text="", error=f"{type(exc).__name__}: {exc}")

        choice = resp.choices[0]
        usage = getattr(resp, "usage", None)
        cost = 0.0
        if usage is not None:
            # OpenRouter tucks cost under usage.cost (USD) when requested.
            cost = float(getattr(usage, "cost", 0.0) or 0.0)
        return Completion(
            text=choice.message.content or "",
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            cost_usd=cost,
        )


class MockClient:
    """Offline client for --dry-run and tests.

    It returns a deterministic, structurally-valid response so scorers run
    for real. If ``echo_gold`` is set, it answers with the task's gold value
    (passed in via the user prompt marker) so a dry run reports ~100% — handy
    for confirming the scoring path end-to-end. Otherwise it returns a fixed
    placeholder so you can see the failure path too.
    """

    def __init__(self, canned: str = "FINAL ANSWER: [dry-run mock answer]"):
        self.canned = canned

    def complete(self, model: str, system: str, user: str) -> Completion:
        # Cheap, deterministic, no network.
        return Completion(text=self.canned, input_tokens=0, output_tokens=0, cost_usd=0.0)
