"""
Functional test configuration.

Tier markers:
  @pytest.mark.tier1  - CI-safe unit tests — no model weights, no Docker, no GPU
  @pytest.mark.tier2  - Credential-dependent tests — requires HF_TOKEN
  @pytest.mark.tier3  - Real tests: docker build, live server, real inference

Module stubs:
  Heavy ML libraries (whisper, torch, pyannote, openvino, librosa, soundfile)
  are stubbed via sys.modules before any test module is imported.  This lets
  tier-1 tests import application code (main, pipeline, components) without
  requiring the full ML stack to be installed in the CI environment.
"""
import csv
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub heavy ML libraries so tier-1 tests can import app code in a
# lightweight CI environment (no torch, whisper, pyannote, openvino).
# Modules already installed take precedence — setdefault is a no-op when
# the real package is present.
# ---------------------------------------------------------------------------
_HEAVY_STUBS = [
    "whisper",
    "whispercpp",
    "torch",
    "torch.serialization",
    "torch.torch_version",
    "pyannote",
    "pyannote.audio",
    "pyannote.audio.core",
    "pyannote.audio.core.task",
    "openvino",
    "openvino_genai",
    "librosa",
    "soundfile",
    "sounddevice",
]
for _mod in _HEAVY_STUBS:
    sys.modules.setdefault(_mod, MagicMock())

# ---------------------------------------------------------------------------

_CSV_PATH = Path(__file__).resolve().parent / "test_results.csv"
_csv_results: list[dict] = []


def pytest_configure(config):
    config.addinivalue_line("markers", "tier1: CI-safe unit tests — no model weights, no Docker, no GPU required")
    config.addinivalue_line("markers", "tier2: credential-dependent tests — requires HF_TOKEN for model download")
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
