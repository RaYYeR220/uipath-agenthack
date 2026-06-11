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
