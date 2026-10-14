"""Shared configuration constants for VIPPET functional tests."""

import os
from pathlib import Path

BASE_URL: str = os.environ.get("VIPPET_BASE_URL", "http://localhost/api/v1")
POLL_TIMEOUT_SECONDS: int = int(os.environ.get("VIPPET_JOB_TIMEOUT_SECONDS", "600"))
POLL_INTERVAL_SECONDS: float = float(os.environ.get("VIPPET_JOB_POLL_INTERVAL", "2.0"))

# A benchmark suite run executes many sequential test cases (one per
# pipeline/variant/stream-count combination), each of which may pay a
# one-off device compile cost (GPU/NPU kernel or blob compilation) on top
# of its fixed run duration. That easily exceeds POLL_TIMEOUT_SECONDS,
# which is sized for a single density/performance job, so suite runs get
# their own, more generous budget.
BENCHMARK_SUITE_POLL_TIMEOUT_SECONDS: int = int(
    os.environ.get("VIPPET_BENCHMARK_SUITE_TIMEOUT_SECONDS", "1800")
)

# Absolute path to the repository root (5 levels up from this file:
# helpers/ -> functional/ -> tests/ -> vippet/ -> <project-root>)
PROJECT_ROOT: Path = Path(__file__).parents[4]

SUPPORTED_MODELS_CATALOG_DIR: Path = PROJECT_ROOT / "vippet" / "models"
DEFAULT_RECORDINGS_YAML: Path = (
    PROJECT_ROOT / "shared" / "videos" / "default_recordings.yaml"
)
