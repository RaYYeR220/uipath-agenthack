from .dimensions.base import DimensionStrategy
from .llm import LLMClient
from .models import MandateSpec, ProbeResult, Scorecard
from .scoring import build_scorecard
from .target import TargetAgent


def run_audit(mandate: MandateSpec, target: TargetAgent,
              dimensions: list[DimensionStrategy], llm: LLMClient) -> Scorecard:
    results: list[ProbeResult] = []
    for dim in dimensions:
        for probe in dim.generate(mandate, llm):
            responses = [target.ask(probe.input) for _ in range(probe.repeat)]
            verdict = dim.judge(probe, responses, mandate, llm)
            results.append(ProbeResult(
                probe_id=probe.id, dimension=probe.dimension, input=probe.input,
                responses=responses, severity=probe.severity,
                passed=verdict.passed, rationale=verdict.rationale,
            ))
    return build_scorecard(mandate.name, results)
