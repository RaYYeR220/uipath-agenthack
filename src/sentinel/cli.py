import argparse
import re
from pathlib import Path

import yaml

from .dimensions import ALL_DIMENSIONS
from .dotenv import load_dotenv
from .llm import AnthropicLLM, LLMClient
from .models import MandateSpec
from .report import write_report
from .runner import audit
from .target import MockTargetAgent, TargetAgent
from .test_manager import publish_audit

# Pattern to detect GUIDs (8-4-4-4-12 hex)
_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _build_llm(model: str) -> LLMClient:
    """Build the Anthropic-backed LLM client."""
    return AnthropicLLM(model=model)


def _build_uipath_llm() -> LLMClient:
    """Seam for tests: build a real UiPathLLM from environment config."""
    from .uipath_agent import UiPathConfig, UiPathLLM

    return UiPathLLM(UiPathConfig.from_env())


def _build_uipath_target(process_key: str) -> TargetAgent:
    """Seam for tests: build a real UiPathTargetAgent from environment config."""
    from .uipath_agent import UiPathAgentClient, UiPathConfig, UiPathTargetAgent

    return UiPathTargetAgent(
        UiPathAgentClient(UiPathConfig.from_env()),
        process_key=process_key,
    )


def _build_test_manager_client():
    """Seam for tests: build a real TestManagerClient from environment config."""
    from .test_manager import TestManagerClient
    from .uipath_agent import UiPathConfig

    return TestManagerClient(UiPathConfig.from_env())


def _build_target(kind: str, mandate: MandateSpec, process_key: str = "LoanAdvisor") -> TargetAgent:
    if kind == "mock":
        return MockTargetAgent(pii_examples=mandate.pii_examples)
    if kind == "uipath":
        return _build_uipath_target(process_key)
    raise SystemExit(f"unknown target '{kind}' — choices: mock, uipath")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="sentinel")
    sub = parser.add_subparsers(dest="command", required=True)
    audit_cmd = sub.add_parser("audit", help="run a reliability audit")
    audit_cmd.add_argument("--mandate", required=True)
    audit_cmd.add_argument("--target", default="mock", choices=["mock", "uipath"])
    audit_cmd.add_argument("--process-key", default="LoanAdvisor",
                           help="UiPath process key (only used with --target uipath)")
    audit_cmd.add_argument("--out", default="report")
    audit_cmd.add_argument("--model", default="claude-sonnet-4-6",
                           help="Model name for --llm anthropic")
    audit_cmd.add_argument("--llm", default="anthropic", choices=["anthropic", "uipath"],
                           help="LLM backend for judges (default: anthropic)")
    audit_cmd.add_argument("--testmanager-project", default=None,
                           help="Test Manager project name or GUID; when set, syncs audit to Test Cloud")
    args = parser.parse_args(argv)

    mandate = MandateSpec(**yaml.safe_load(Path(args.mandate).read_text(encoding="utf-8")))

    if args.llm == "uipath":
        llm = _build_uipath_llm()
    else:
        llm = _build_llm(args.model)

    target = _build_target(args.target, mandate, args.process_key)
    results, scorecard = audit(mandate, target, ALL_DIMENSIONS, llm)
    paths = write_report(scorecard, Path(args.out))
    print(f"{mandate.name}: {scorecard.overall}/100 ({scorecard.light}). "
          f"Report: {paths[0]}")

    if args.testmanager_project:
        tm_client = _build_test_manager_client()
        project_id = args.testmanager_project
        if not _GUID_RE.match(project_id):
            resolved = tm_client.find_project_id(project_id)
            if resolved is None:
                print(f"WARNING: Test Manager project '{project_id}' not found; skipping sync.")
                return 0
            project_id = resolved

        summary = publish_audit(tm_client, project_id, mandate.name, results)
        print(f"Test Manager sync: {summary['test_cases_created']} test cases created, "
              f"execution_id={summary['execution_id']}, "
              f"results_logged={summary['results_logged']}")
        if summary.get("warning"):
            print(f"WARNING: {summary['warning']}")

    return 0
