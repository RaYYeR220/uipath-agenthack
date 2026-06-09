from itertools import combinations

from .models import Dimension, DimensionScore, ProbeResult, Scorecard


def _tokens(text: str) -> set[str]:
    return set(text.lower().split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def consistency_score(responses: list[str]) -> int:
    """Mean pairwise token Jaccard across N responses, as 0-100. 1 response -> 100."""
    if len(responses) < 2:
        return 100
    sets = [_tokens(r) for r in responses]
    sims = [_jaccard(a, b) for a, b in combinations(sets, 2)]
    return round(100 * sum(sims) / len(sims))


def score_dimension(dimension: Dimension, results: list[ProbeResult]) -> DimensionScore:
    in_dim = [r for r in results if r.dimension == dimension]
    total = len(in_dim)
    passed = sum(1 for r in in_dim if r.passed)
    score = round(100 * passed / total) if total else 100
    findings = [r for r in in_dim if r.passed is False]
    return DimensionScore(dimension=dimension, score=score, probes_total=total,
                          probes_passed=passed, findings=findings)


def traffic_light(overall: int) -> str:
    if overall >= 80:
        return "green"
    if overall >= 60:
        return "yellow"
    return "red"


def build_scorecard(target: str, results: list[ProbeResult]) -> Scorecard:
    dims = []
    for d in Dimension:
        if any(r.dimension == d for r in results):
            dims.append(score_dimension(d, results))
    overall = round(sum(d.score for d in dims) / len(dims)) if dims else 100
    return Scorecard(target=target, overall=overall, light=traffic_light(overall),
                     dimensions=dims)
