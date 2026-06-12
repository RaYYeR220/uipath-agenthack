"""Publish Sentinel's per-probe verdicts as NATIVE Test Manager results.

Sentinel is itself the test runner: it fires probes at the target agent (via the
Orchestrator Jobs API) and judges each one. This script takes those verdicts —
read from a saved `report/scorecard.json` — and writes them into a UiPath Test
Manager *manual execution* as native Passed/Failed results, by driving the
official `uip` CLI (`uip tm testcaselog finish`).

Why the CLI and not raw REST: the Test Manager v2 `POST /testexecutions`
(ThirdParty source) path 500s on the AgentHack staging tenant. A manual
execution created from a Test Set + `testcaselog finish` is the supported path,
and the official CLI gets the envelope/auth right. This needs NO test-automation
robot slot — the verdicts come from Sentinel, the executor.

Prereq: `uip login` (see uip-cli-staging memory) and a manual execution created
from the test set, e.g.:

    uip tm testsets run --test-set-key SLA:27 --execution-type manual

Usage:
    python scripts/sync_native_results.py \
        --project-key SLA \
        --execution-id <uuid> \
        --executed-by you@example.com \
        --scorecard report/scorecard.json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys

# Test cases named "[dimension] probe_id"; seeds have free-form names.
_PROBE_NAME = re.compile(r"^\[[^\]]+\]\s*(?P<probe_id>\S+)\s*$")


def failed_probe_ids(scorecard: dict) -> set[str]:
    """Probe ids that failed, taken from each dimension's findings list."""
    return {
        f["probe_id"]
        for dim in scorecard.get("dimensions", [])
        for f in dim.get("findings", [])
        if "probe_id" in f
    }


def verdict_passed(name: str, failed_ids: set[str], seed_fail_names: set[str]) -> bool:
    """Decide PASS/FAIL for a test case by its name.

    - "[dim] probe_id"  -> fail iff probe_id is in the audit's failed set.
    - free-form seed    -> fail iff its name is in seed_fail_names, else pass.
    """
    m = _PROBE_NAME.match(name)
    if m:
        return m.group("probe_id") not in failed_ids
    return name not in seed_fail_names


# Seed test cases (created during TM integration bring-up) keyed by exact name.
# The cross-customer probe leaked Jane Smith's SSN in the live audit -> Failed.
SEED_FAIL_NAMES = {"PII cross-customer leak probe"}


def _uip() -> str:
    path = shutil.which("uip") or shutil.which("uip.cmd")
    if not path:
        sys.exit("uip CLI not found on PATH — run `uip login` first.")
    return path


def list_testcase_logs(uip: str, project_key: str, execution_id: str) -> list[dict]:
    out = subprocess.run(
        [uip, "tm", "executions", "testcaselogs", "list",
         "--execution-id", execution_id, "--project-key", project_key,
         "--output", "json"],
        capture_output=True, text=True, check=True,
    ).stdout
    # The CLI prints a "Resolved project ..." preamble before the JSON.
    payload = json.loads(out[out.index("{"):])
    return payload["Data"]


def finish_log(uip: str, project_key: str, execution_id: str, test_case_id: str,
               passed: bool, executed_by: str) -> None:
    subprocess.run(
        [uip, "tm", "testcaselog", "finish",
         "--project-key", project_key,
         "--execution-id", execution_id,
         "--test-case-id", test_case_id,
         "--result", "Passed" if passed else "Failed",
         "--has-error", "false" if passed else "true",
         "--executed-by", executed_by,
         "--output", "json"],
        capture_output=True, text=True, check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-key", required=True)
    ap.add_argument("--execution-id", required=True)
    ap.add_argument("--executed-by", required=True)
    ap.add_argument("--scorecard", default="report/scorecard.json")
    args = ap.parse_args()

    with open(args.scorecard, encoding="utf-8") as fh:
        scorecard = json.load(fh)
    failed_ids = failed_probe_ids(scorecard)

    uip = _uip()
    logs = list_testcase_logs(uip, args.project_key, args.execution_id)

    passed_n = failed_n = 0
    for log in logs:
        tc = log["TestCase"]
        name, tc_id, obj = tc["Name"], log["TestCaseId"], tc["ObjKey"]
        passed = verdict_passed(name, failed_ids, SEED_FAIL_NAMES)
        finish_log(uip, args.project_key, args.execution_id, tc_id, passed, args.executed_by)
        passed_n, failed_n = passed_n + passed, failed_n + (not passed)
        print(f"  {obj:<8} {'PASS' if passed else 'FAIL'}  {name}")

    print(f"\nSynced {len(logs)} native results: {passed_n} Passed, {failed_n} Failed.")


if __name__ == "__main__":
    main()
