# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Simple file-backed telemetry store shared across Gunicorn workers."""

import fcntl
import json
from pathlib import Path
from typing import Any, Dict, List

from src.utils.common import settings

_DEFAULT_PATH = Path(settings.VLM_TELEMETRY_PATH)
_MAX_RECORDS = settings.VLM_TELEMETRY_MAX_RECORDS


class TelemetryStore:
    """Append-only JSONL store with file locking and bounded history."""

    def __init__(self, path: Path | None = None, max_records: int = _MAX_RECORDS):
        """Configure on-disk storage location and retention budget."""
        self.path = path or _DEFAULT_PATH
        self.max_records = max_records

    def _ensure_parent(self) -> None:
        """Create parent directories for the telemetry file if needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: Dict[str, Any]) -> None:
        """Append a telemetry record and keep only the most recent entries."""

        self._ensure_parent()
        serialized = json.dumps(record, ensure_ascii=False)
        with open(self.path, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.seek(0)
                lines = [line.rstrip("\n") for line in handle.readlines() if line.strip()]
                lines.append(serialized)
                if len(lines) > self.max_records:
                    lines = lines[-self.max_records :]
                handle.seek(0)
                handle.truncate()
                handle.write("\n".join(lines))
                handle.write("\n")
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def read_all(self) -> List[Dict[str, Any]]:
        """Return stored telemetry entries (oldest first)."""

        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                return [json.loads(line) for line in handle if line.strip()]
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


telemetry_store = TelemetryStore()
