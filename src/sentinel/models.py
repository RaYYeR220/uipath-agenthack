from enum import Enum
from pydantic import BaseModel


class Dimension(str, Enum):
    HALLUCINATION = "hallucination"
    INJECTION = "injection"
    NONDETERMINISM = "nondeterminism"
    PII_LEAK = "pii_leak"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MandateSpec(BaseModel):
    name: str
    role: str
    allowed_actions: list[str] = []
    forbidden_actions: list[str] = []
    grounding_facts: list[str] = []      # ground-truth the agent must not contradict
    pii_examples: list[str] = []         # PII strings that must never leak (bait + detection)


class Probe(BaseModel):
    id: str
    dimension: Dimension
    input: str
    severity: Severity = Severity.MEDIUM
    repeat: int = 1
    rule: dict = {}                      # verdict-strategy params per dimension


class ProbeResult(BaseModel):
    probe_id: str
    dimension: Dimension
    input: str
    responses: list[str] = []
    severity: Severity = Severity.MEDIUM
    passed: bool | None = None
    rationale: str = ""


class Verdict(BaseModel):
    passed: bool
    rationale: str = ""


class DimensionScore(BaseModel):
    dimension: Dimension
    score: int                           # 0-100
    probes_total: int
    probes_passed: int
    findings: list[ProbeResult] = []     # failed probes only (evidence)


class Scorecard(BaseModel):
    target: str
    overall: int                         # 0-100
    light: str                           # "green" | "yellow" | "red"
    dimensions: list[DimensionScore] = []
