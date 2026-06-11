import argparse
from pathlib import Path

import yaml

from .dimensions import ALL_DIMENSIONS
from .llm import AnthropicLLM, LLMClient
from .models import MandateSpec
from .report import write_report
from .runner import run_audit
from .target import MockTargetAgent, TargetAgent


def _build_llm(model: str) -> LLMClient:
    return AnthropicLLM(model=model)


def _build_uipath_target(process_key: str) -> TargetAgent:
    """Seam for tests: build a real UiPathTargetAgent from environment config."""
    from .uipath_agent import UiPathAgentClient, UiPathConfig, UiPathTargetAgent

    return UiPathTargetAgent(
        UiPathAgentClient(UiPathConfig.from_env()),
        process_key=process_key,
    )


def _build_target(kind: str, mandate: MandateSpec, process_key: str = "LoanAdvisor") -> TargetAgent:
    if kind == "mock":
        return MockTargetAgent(pii_examples=mandate.pii_examples)
    if kind == "uipath":
        return _build_uipath_target(process_key)
    raise SystemExit(f"unknown target '{kind}' — choices: mock, uipath")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentinel")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="run a reliability audit")
    audit.add_argument("--mandate", required=True)
    audit.add_argument("--target", default="mock", choices=["mock", "uipath"])
    audit.add_argument("--process-key", default="LoanAdvisor",
                       help="UiPath process key (only used with --target uipath)")
    audit.add_argument("--out", default="report")
    audit.add_argument("--model", default="claude-sonnet-4-6")
    args = parser.parse_args(argv)

    mandate = MandateSpec(**yaml.safe_load(Path(args.mandate).read_text(encoding="utf-8")))
    llm = _build_llm(args.model)
    target = _build_target(args.target, mandate, args.process_key)
    scorecard = run_audit(mandate, target, ALL_DIMENSIONS, llm)
    paths = write_report(scorecard, Path(args.out))
    print(f"{mandate.name}: {scorecard.overall}/100 ({scorecard.light}). "
          f"Report: {paths[0]}")
    return 0
