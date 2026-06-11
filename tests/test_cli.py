"""Tests for CLI main() — no network, no LLM calls, no real UiPath env."""
import json
from pathlib import Path

import pytest

import sentinel.cli as cli_module
from sentinel.cli import main
from sentinel.target import MockTargetAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeTarget:
    """Minimal TargetAgent for CLI wiring tests."""
    def ask(self, message: str) -> str:
        return "I can help with loan information."


class _FakeLLM:
    """Returns valid JSON for hallucination probes, refuse-style for judge calls."""
    def complete(self, system: str, user: str) -> str:
        # HallucinationDimension generate() expects a JSON list of questions
        if "JSON array" in system:
            return '["What is the APR for a home loan?"]'
        # InjectionDimension LLM-judge expects {"passed": bool, "rationale": str}
        return '{"passed": true, "rationale": "ok"}'


# ---------------------------------------------------------------------------
# --target mock (regression: must still work)
# ---------------------------------------------------------------------------

def test_mock_target_audit_writes_scorecard(tmp_path, monkeypatch):
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"

    # Stub _build_llm so we never call Anthropic
    monkeypatch.setattr(cli_module, "_build_llm", lambda model: _FakeLLM())

    out = tmp_path / "scorecard"
    rc = main([
        "audit",
        "--mandate", str(mandate_path),
        "--target", "mock",
        "--out", str(out),
    ])
    assert rc == 0
    assert (out / "scorecard.md").exists()


# ---------------------------------------------------------------------------
# --target uipath (fake-injected, no network)
# ---------------------------------------------------------------------------

def test_uipath_target_audit_writes_scorecard(tmp_path, monkeypatch):
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"

    # Patch both LLM and the UiPath-target seam
    monkeypatch.setattr(cli_module, "_build_llm", lambda model: _FakeLLM())
    monkeypatch.setattr(cli_module, "_build_uipath_target",
                        lambda process_key: _FakeTarget())

    out = tmp_path / "scorecard"
    rc = main([
        "audit",
        "--mandate", str(mandate_path),
        "--target", "uipath",
        "--process-key", "LoanAdvisor",
        "--out", str(out),
    ])
    assert rc == 0
    assert (out / "scorecard.md").exists()


def test_uipath_target_uses_process_key_arg(tmp_path, monkeypatch):
    """The process_key CLI arg is forwarded to _build_uipath_target."""
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"
    captured = {}

    def fake_build(process_key: str):
        captured["process_key"] = process_key
        return _FakeTarget()

    monkeypatch.setattr(cli_module, "_build_llm", lambda model: _FakeLLM())
    monkeypatch.setattr(cli_module, "_build_uipath_target", fake_build)

    out = tmp_path / "scorecard"
    main([
        "audit",
        "--mandate", str(mandate_path),
        "--target", "uipath",
        "--process-key", "MyCustomProcess",
        "--out", str(out),
    ])
    assert captured["process_key"] == "MyCustomProcess"


def test_uipath_target_default_process_key(tmp_path, monkeypatch):
    """--process-key defaults to 'LoanAdvisor' when not specified."""
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"
    captured = {}

    def fake_build(process_key: str):
        captured["process_key"] = process_key
        return _FakeTarget()

    monkeypatch.setattr(cli_module, "_build_llm", lambda model: _FakeLLM())
    monkeypatch.setattr(cli_module, "_build_uipath_target", fake_build)

    out = tmp_path / "scorecard"
    main([
        "audit",
        "--mandate", str(mandate_path),
        "--target", "uipath",
        "--out", str(out),
    ])
    assert captured["process_key"] == "LoanAdvisor"


def test_invalid_target_rejected(tmp_path):
    """An unrecognised --target value raises SystemExit from argparse."""
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"
    with pytest.raises(SystemExit):
        main([
            "audit",
            "--mandate", str(mandate_path),
            "--target", "nonexistent",
        ])


# ---------------------------------------------------------------------------
# --llm uipath (gateway-backed judge, no network)
# ---------------------------------------------------------------------------

def test_llm_uipath_audit_writes_scorecard(tmp_path, monkeypatch):
    """--llm uipath uses the monkeypatched _build_uipath_llm seam, no network."""
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"

    monkeypatch.setattr(cli_module, "_build_uipath_llm", lambda: _FakeLLM())
    monkeypatch.setattr(cli_module, "_build_uipath_target",
                        lambda process_key: _FakeTarget())

    out = tmp_path / "scorecard"
    rc = main([
        "audit",
        "--mandate", str(mandate_path),
        "--target", "mock",
        "--llm", "uipath",
        "--out", str(out),
    ])
    assert rc == 0
    assert (out / "scorecard.md").exists()


def test_llm_uipath_seam_called(tmp_path, monkeypatch):
    """When --llm uipath is passed, _build_uipath_llm is called (not _build_llm)."""
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"
    called = {"uipath_llm": False, "anthropic_llm": False}

    def fake_uipath_llm():
        called["uipath_llm"] = True
        return _FakeLLM()

    def fake_anthropic_llm(model):
        called["anthropic_llm"] = True
        return _FakeLLM()

    monkeypatch.setattr(cli_module, "_build_uipath_llm", fake_uipath_llm)
    monkeypatch.setattr(cli_module, "_build_llm", fake_anthropic_llm)

    out = tmp_path / "scorecard"
    main([
        "audit",
        "--mandate", str(mandate_path),
        "--target", "mock",
        "--llm", "uipath",
        "--out", str(out),
    ])
    assert called["uipath_llm"] is True
    assert called["anthropic_llm"] is False


def test_llm_anthropic_default_unchanged(tmp_path, monkeypatch):
    """Default --llm anthropic still calls _build_llm (not _build_uipath_llm)."""
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"
    called = {"uipath_llm": False, "anthropic_llm": False}

    def fake_uipath_llm():
        called["uipath_llm"] = True
        return _FakeLLM()

    def fake_anthropic_llm(model):
        called["anthropic_llm"] = True
        return _FakeLLM()

    monkeypatch.setattr(cli_module, "_build_uipath_llm", fake_uipath_llm)
    monkeypatch.setattr(cli_module, "_build_llm", fake_anthropic_llm)

    out = tmp_path / "scorecard"
    main([
        "audit",
        "--mandate", str(mandate_path),
        "--target", "mock",
        "--out", str(out),
    ])
    assert called["anthropic_llm"] is True
    assert called["uipath_llm"] is False


def test_invalid_llm_rejected(tmp_path):
    """An unrecognised --llm value raises SystemExit from argparse."""
    mandate_path = Path(__file__).parent.parent / "mandates" / "loanadvisor.yaml"
    with pytest.raises(SystemExit):
        main([
            "audit",
            "--mandate", str(mandate_path),
            "--llm", "openai",
        ])
