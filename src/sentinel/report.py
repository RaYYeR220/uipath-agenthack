from pathlib import Path

from .models import Scorecard

_LIGHT_EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def scorecard_to_markdown(sc: Scorecard) -> str:
    lines = [
        f"# Reliability Scorecard — {sc.target}",
        "",
        f"**Overall: {sc.overall}/100 {_LIGHT_EMOJI.get(sc.light, '')} ({sc.light})**",
        "",
        "| Dimension | Score | Passed/Total |",
        "| --- | --- | --- |",
    ]
    for d in sc.dimensions:
        lines.append(f"| {d.dimension.value} | {d.score} | {d.probes_passed}/{d.probes_total} |")
    lines.append("")
    findings = [f for d in sc.dimensions for f in d.findings]
    if findings:
        lines.append("## Findings")
        for f in findings:
            lines += [
                f"### {f.probe_id} ({f.dimension.value}, {f.severity.value})",
                f"- **Input:** {f.input}",
                f"- **Response:** {f.responses[0] if f.responses else ''}",
                f"- **Verdict:** {f.rationale}",
                "",
            ]
    return "\n".join(lines)


def scorecard_to_json(sc: Scorecard) -> str:
    return sc.model_dump_json(indent=2)


def write_report(sc: Scorecard, outdir: Path) -> list[Path]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    md_path = outdir / "scorecard.md"
    json_path = outdir / "scorecard.json"
    md_path.write_text(scorecard_to_markdown(sc), encoding="utf-8")
    json_path.write_text(scorecard_to_json(sc), encoding="utf-8")
    return [md_path, json_path]
