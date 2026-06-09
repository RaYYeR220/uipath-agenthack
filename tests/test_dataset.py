import csv
from sentinel.models import Dimension, Probe, Severity
from sentinel.dataset import probes_to_rows, write_probe_csv, read_results_csv

def test_probes_to_rows_shape():
    probes = [Probe(id="inj-1", dimension=Dimension.INJECTION, input="x", repeat=2,
                    severity=Severity.HIGH)]
    rows = probes_to_rows(probes)
    assert rows[0] == {"probe_id": "inj-1", "dimension": "injection",
                       "input": "x", "repeat": "2", "severity": "high"}

def test_write_probe_csv_roundtrips(tmp_path):
    probes = [Probe(id="pii-1", dimension=Dimension.PII_LEAK, input="leak?", repeat=1)]
    path = tmp_path / "probes.csv"
    write_probe_csv(probes, path)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["probe_id"] == "pii-1" and rows[0]["input"] == "leak?"

def test_read_results_csv_groups_by_probe(tmp_path):
    path = tmp_path / "results.csv"
    path.write_text("probe_id,run_index,response\n"
                    "nd-1,0,Yes\nnd-1,1,No\npii-1,0,refused\n", encoding="utf-8")
    grouped = read_results_csv(path)
    assert grouped == {"nd-1": ["Yes", "No"], "pii-1": ["refused"]}
