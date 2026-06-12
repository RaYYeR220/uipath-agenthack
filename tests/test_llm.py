import json

import pytest

from sentinel.llm import FakeLLM, LLMClient, OfflineLLM


def test_fakellm_returns_canned_in_order():
    llm = FakeLLM(["first", "second"])
    assert llm.complete("sys", "u1") == "first"
    assert llm.complete("sys", "u2") == "second"


def test_fakellm_records_calls():
    llm = FakeLLM("only")
    llm.complete("SYS", "USER")
    assert llm.calls == [("SYS", "USER")]
    assert llm.complete("a", "b") == "only"  # single string repeats


# ---------------------------------------------------------------------------
# OfflineLLM
# ---------------------------------------------------------------------------

def test_offlinellm_satisfies_llmclient_protocol():
    llm = OfflineLLM()
    assert isinstance(llm, LLMClient)


def test_offlinellm_returns_json_array_when_system_mentions_array():
    llm = OfflineLLM()
    result = llm.complete(
        system="Return ONLY a JSON array of question strings.",
        user="some user prompt",
    )
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) > 0
    assert all(isinstance(q, str) for q in parsed)


def test_offlinellm_returns_passed_true_object_for_judge_prompts():
    llm = OfflineLLM()
    result = llm.complete(
        system='You are a QA judge. Reply with {"passed": bool, "rationale": str}.',
        user="PROBE: something\nRESPONSE: something",
    )
    parsed = json.loads(result)
    assert isinstance(parsed, dict)
    assert parsed["passed"] is True
    assert "rationale" in parsed


def test_offlinellm_is_deterministic():
    """Same inputs always produce the same output."""
    llm = OfflineLLM()
    r1 = llm.complete("Return ONLY a JSON array of strings.", "user")
    r2 = llm.complete("Return ONLY a JSON array of strings.", "user")
    assert r1 == r2


def test_offlinellm_judge_output_is_deterministic():
    llm = OfflineLLM()
    r1 = llm.complete('Reply with {"passed": bool}', "response")
    r2 = llm.complete('Reply with {"passed": bool}', "response")
    assert r1 == r2


def test_offlinellm_requires_no_constructor_args():
    """OfflineLLM can be constructed with zero arguments."""
    llm = OfflineLLM()
    assert llm is not None
