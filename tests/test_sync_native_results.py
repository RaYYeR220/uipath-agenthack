"""Tests for the verdict-derivation logic in scripts/sync_native_results.py.

Only the pure functions are covered — the subprocess/uip plumbing is exercised
live, not in unit tests (no network/CLI in the test suite).
"""
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_native_results.py"
_spec = importlib.util.spec_from_file_location("sync_native_results", _SCRIPT)
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)


def test_failed_probe_ids_collects_from_all_dimension_findings():
    scorecard = {
        "dimensions": [
            {"dimension": "hallucination", "findings": []},
            {"dimension": "nondeterminism", "findings": [
                {"probe_id": "nd-1"}, {"probe_id": "nd-2"}]},
            {"dimension": "pii_leak", "findings": [
                {"probe_id": "pii-4"}, {"probe_id": "pii-6"}]},
        ]
    }
    assert sync.failed_probe_ids(scorecard) == {"nd-1", "nd-2", "pii-4", "pii-6"}


def test_failed_probe_ids_empty_when_no_findings():
    assert sync.failed_probe_ids({"dimensions": [{"findings": []}]}) == set()


def test_verdict_dimension_probe_passes_when_not_in_failed_set():
    assert sync.verdict_passed("[injection] inj-1", {"pii-4"}, set()) is True


def test_verdict_dimension_probe_fails_when_in_failed_set():
    assert sync.verdict_passed("[pii_leak] pii-4", {"pii-4"}, set()) is False


def test_verdict_handles_whitespace_in_name():
    assert sync.verdict_passed("[nondeterminism]  nd-2", {"nd-2"}, set()) is False


def test_seed_passes_by_default():
    assert sync.verdict_passed("SLA smoke probe", {"pii-4"}, sync.SEED_FAIL_NAMES) is True


def test_seed_in_fail_list_fails():
    assert sync.verdict_passed(
        "PII cross-customer leak probe", set(), sync.SEED_FAIL_NAMES) is False
