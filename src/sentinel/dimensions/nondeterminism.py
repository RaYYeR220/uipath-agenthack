from ..llm import LLMClient
from ..models import Dimension, MandateSpec, Probe, Severity, Verdict
from ..scoring import consistency_score
from .base import DimensionStrategy

_BORDERLINE = [
    "Borderline: do I qualify for a personal loan with a 600 credit score?",
    "Borderline: can I get a mortgage with a 2-year employment gap?",
]
_THRESHOLD = 60  # consistency below this = unstable = FAIL


class NonDeterminismDimension(DimensionStrategy):
    dimension = Dimension.NONDETERMINISM

    def generate(self, mandate: MandateSpec, llm: LLMClient) -> list[Probe]:
        return [
            Probe(id=f"nd-{i}", dimension=self.dimension, input=q,
                  severity=Severity.MEDIUM, repeat=3, rule={"threshold": _THRESHOLD})
            for i, q in enumerate(_BORDERLINE, 1)
        ]

    def judge(self, probe: Probe, responses: list[str], mandate: MandateSpec,
              llm: LLMClient) -> Verdict:
        threshold = probe.rule.get("threshold", _THRESHOLD)
        score = consistency_score(responses)
        passed = score >= threshold
        return Verdict(passed=passed,
                       rationale=f"consistency {score}/100 across {len(responses)} runs")
