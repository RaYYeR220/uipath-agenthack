import csv
from collections import defaultdict
from pathlib import Path

from .models import Probe

PROBE_FIELDS = ["probe_id", "dimension", "input", "repeat", "severity"]


def probes_to_rows(probes: list[Probe]) -> list[dict]:
    return [
        {"probe_id": p.id, "dimension": p.dimension.value, "input": p.input,
         "repeat": str(p.repeat), "severity": p.severity.value}
        for p in probes
    ]


def write_probe_csv(probes: list[Probe], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PROBE_FIELDS)
        writer.writeheader()
        writer.writerows(probes_to_rows(probes))


def read_results_csv(path: Path) -> dict[str, list[str]]:
    """Reads rows (probe_id, run_index, response) -> {probe_id: [responses ordered by run_index]}."""
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["probe_id"]].append((int(row["run_index"]), row["response"]))
    return {pid: [resp for _, resp in sorted(pairs)] for pid, pairs in grouped.items()}
