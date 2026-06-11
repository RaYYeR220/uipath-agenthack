from .dimensions.base import DimensionStrategy
from .llm import LLMClient
from .models import MandateSpec, ProbeResult, Scorecard
from .scoring import build_scorecard
from .target import TargetAgent


def audit(mandate: MandateSpec, target: TargetAgent,
          dimensions: list[DimensionStrategy], llm: LLMClient) -> tuple[list[ProbeResult], Scorecard]:
    """Run the full audit probe loop.

    Returns both the raw ProbeResult list and the computed Scorecard.
    Use this when callers need the individual results (e.g. for Test Manager sync).
    """
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
    return results, build_scorecard(mandate.name, results)


def run_audit(mandate: MandateSpec, target: TargetAgent,
              dimensions: list[DimensionStrategy], llm: LLMClient) -> Scorecard:
    """Run audit and return only the Scorecard. Preserved for backward compatibility."""
    _, scorecard = audit(mandate, target, dimensions, llm)
    return scorecard
