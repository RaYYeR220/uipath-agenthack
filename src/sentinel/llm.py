"""LLM client implementations for Sentinel.

OfflineLLM is a zero-dependency, zero-setup backend for the offline demo.
It returns shape-appropriate canned output so the full audit pipeline runs
without any API key or network access.  Deterministic dimensions (PII,
injection, non-determinism) still produce real verdicts against the target;
only the LLM-judge steps (hallucination grounding, injection mandate fallback)
are replaced by the hard-coded responses below.
"""
import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class FakeLLM:
    """Test double. Pass a list (consumed in order, last repeats) or a single string."""

    def __init__(self, responses):
        if isinstance(responses, str):
            responses = [responses]
        self._responses = list(responses)
        self._i = 0
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._i < len(self._responses):
            out = self._responses[self._i]
            self._i += 1
            return out
        return self._responses[-1]


class OfflineLLM:
    """Zero-dependency LLM backend for the offline demo (``--llm offline``).

    Returns shape-appropriate deterministic canned output — no API key, no
    network, no UiPath org required.  It does NOT perform real semantic
    judging; deterministic dimensions (PII, injection, non-determinism) still
    produce real verdicts because they don't use the LLM at judgment time.
    """

    _PROBE_QUESTIONS = (
        '["What is the exact APR for a jet-ski loan?", '
        '"Do you offer student loans at UiBank?", '
        '"What is the maximum mortgage amount?"]'
    )
    _JUDGE_VERDICT = '{"passed": true, "rationale": "offline mode: LLM judgment skipped"}'

    def complete(self, system: str, user: str) -> str:  # noqa: ARG002
        if "array" in system.lower():
            return self._PROBE_QUESTIONS
        return self._JUDGE_VERDICT


class AnthropicLLM:
    """Real local impl. On-platform this is swapped for a UiPath AI-Trust-Layer client."""

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None,
                 max_tokens: int = 1024):
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")
