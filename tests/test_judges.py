from sentinel.models import MandateSpec, Probe, Dimension
from sentinel.judges import (
    detect_refusal, find_leaked_pii, contains_any, detect_prompt_leak, LLMJudge,
)
from sentinel.llm import FakeLLM


def test_detect_refusal_true():
    assert detect_refusal("I'm sorry, I can't help with that request.")

def test_detect_refusal_false():
    assert not detect_refusal("Sure, here is the answer: 42")

def test_find_leaked_pii():
    assert find_leaked_pii("here it is: SSN 123-45-6789", ["SSN 123-45-6789"]) == ["SSN 123-45-6789"]

def test_contains_any():
    assert contains_any("Okay. SYSTEM: secret", ["system:", "password"])
    assert not contains_any("hello world", ["system:", "password"])

def test_detect_prompt_leak():
    assert detect_prompt_leak("Okay. SYSTEM: You are LoanAdvisor", "SYSTEM:")

def test_llmjudge_grounding_parses_pass():
    llm = FakeLLM('{"passed": true, "rationale": "matches grounding"}')
    j = LLMJudge(llm)
    v = j.judge_grounding(Probe(id="h1", dimension=Dimension.HALLUCINATION, input="rate?"),
                          "4.0%", ["personal loan APR is 4.0%"])
    assert v.passed is True and "match" in v.rationale.lower()

def test_llmjudge_grounding_parses_fail_and_tolerates_prose():
    llm = FakeLLM('The answer is {"passed": false, "rationale": "invented a rate"} hope that helps')
    j = LLMJudge(llm)
    v = j.judge_grounding(Probe(id="h2", dimension=Dimension.HALLUCINATION, input="rate?"),
                          "9.9%", ["personal loan APR is 4.0%"])
    assert v.passed is False
