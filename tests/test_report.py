import json
from sentinel.models import Dimension, DimensionScore, ProbeResult, Scorecard, Severity
from sentinel.report import scorecard_to_markdown, scorecard_to_json, write_report

def _scorecard():
    finding = ProbeResult(probe_id="inj-1", dimension=Dimension.INJECTION, input="ignore rules",
                          responses=["SYSTEM: ..."], passed=False, rationale="leaked",
                          severity=Severity.HIGH)
    return Scorecard(target="LoanAdvisor", overall=55, light="red", dimensions=[
        DimensionScore(dimension=Dimension.INJECTION, score=0, probes_total=1,
                       probes_passed=0, findings=[finding]),
    ])

def test_markdown_has_target_light_and_finding():
    md = scorecard_to_markdown(_scorecard())
    assert "LoanAdvisor" in md and "red" in md.lower()
    assert "55" in md and "inj-1" in md and "leaked" in md

def test_json_is_valid_and_roundtrips():
    data = json.loads(scorecard_to_json(_scorecard()))
    assert data["overall"] == 55 and data["dimensions"][0]["score"] == 0

def test_write_report_creates_both_files(tmp_path):
    paths = write_report(_scorecard(), tmp_path)
    assert (tmp_path / "scorecard.md").exists()
    assert (tmp_path / "scorecard.json").exists()
    assert set(paths) == {tmp_path / "scorecard.md", tmp_path / "scorecard.json"}
