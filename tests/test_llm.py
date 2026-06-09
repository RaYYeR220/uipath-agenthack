from sentinel.llm import FakeLLM


def test_fakellm_returns_canned_in_order():
    llm = FakeLLM(["first", "second"])
    assert llm.complete("sys", "u1") == "first"
    assert llm.complete("sys", "u2") == "second"


def test_fakellm_records_calls():
    llm = FakeLLM("only")
    llm.complete("SYS", "USER")
    assert llm.calls == [("SYS", "USER")]
    assert llm.complete("a", "b") == "only"  # single string repeats
