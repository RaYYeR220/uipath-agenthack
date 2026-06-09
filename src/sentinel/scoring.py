from itertools import combinations


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
