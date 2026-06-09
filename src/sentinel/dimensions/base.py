from abc import ABC, abstractmethod

from ..llm import LLMClient
from ..models import Dimension, MandateSpec, Probe, Verdict


class DimensionStrategy(ABC):
    """A reliability dimension owns BOTH probe generation and response judging."""

    dimension: Dimension

    @abstractmethod
    def generate(self, mandate: MandateSpec, llm: LLMClient) -> list[Probe]:
        ...

    @abstractmethod
    def judge(self, probe: Probe, responses: list[str], mandate: MandateSpec,
              llm: LLMClient) -> Verdict:
        ...
