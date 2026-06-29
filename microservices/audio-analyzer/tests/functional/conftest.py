"""
Functional test configuration.

Tier markers:
  @pytest.mark.tier3  - Real tests: docker build, live server, real inference
"""
import csv
import re
from pathlib import Path

import pytest

_CSV_PATH = Path(__file__).resolve().parent / "test_results.csv"
_csv_results: list[dict] = []


def pytest_configure(config):
    config.addinivalue_line("markers", "tier3: real functional tests — docker, live server, inference")


def _humanize(nodeid: str) -> str:
    """Convert pytest node-id to a readable one-liner."""
    parts = nodeid.split("::")
    parts[0] = parts[0].replace(".py", "").replace("/", " > ").replace("\\", " > ")
    label = " > ".join(parts)
    label = re.sub(r"\btest_", "", label)
    return label.replace("_", " ")


def pytest_runtest_logreport(report):
    if report.skipped:
        if not any(r["nodeid"] == report.nodeid for r in _csv_results):
            _csv_results.append({"nodeid": report.nodeid,
                                  "description": _humanize(report.nodeid),
                                  "status": "SKIP"})
        return
    if report.when != "call":
        return
    _csv_results.append({
        "nodeid": report.nodeid,
        "description": _humanize(report.nodeid),
        "status": "PASS" if report.passed else "FAIL",
    })


def pytest_sessionfinish(session, exitstatus):
    if not _csv_results:
        return
    _CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CSV_PATH, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["description", "status"])
        writer.writeheader()
        writer.writerows({"description": r["description"], "status": r["status"]}
                         for r in _csv_results)
    print(f"\n📄 CSV report → {_CSV_PATH}")
