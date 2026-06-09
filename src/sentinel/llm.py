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
