"""Shared configuration constants for VIPPET functional tests."""

import os
from pathlib import Path

BASE_URL: str = os.environ.get("VIPPET_BASE_URL", "http://localhost/api/v1")
POLL_TIMEOUT_SECONDS: int = int(os.environ.get("VIPPET_JOB_TIMEOUT_SECONDS", "600"))
POLL_INTERVAL_SECONDS: float = float(os.environ.get("VIPPET_JOB_POLL_INTERVAL", "2.0"))

# Absolute path to the repository root (5 levels up from this file:
# helpers/ -> functional/ -> tests/ -> vippet/ -> <project-root>)
PROJECT_ROOT: Path = Path(__file__).parents[4]

SUPPORTED_MODELS_YAML: Path = (
    PROJECT_ROOT / "shared" / "models" / "supported_models.yaml"
)
DEFAULT_RECORDINGS_YAML: Path = (
    PROJECT_ROOT / "shared" / "videos" / "default_recordings.yaml"
)
