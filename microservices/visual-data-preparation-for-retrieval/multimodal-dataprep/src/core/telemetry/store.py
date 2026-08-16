# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""File-backed telemetry storage with POSIX locks."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any, Dict, List

from src.common import settings


class TelemetryStore:
	"""Append-only JSONL store guarded by advisory file locks."""

	def __init__(self, path: Path | str, max_records: int) -> None:
		self.path = Path(path)
		self.max_records = max_records

	def _ensure_parent(self) -> None:
		self.path.parent.mkdir(parents=True, exist_ok=True)

	def append(self, record: Dict[str, Any]) -> None:
		"""Persist a telemetry record, keeping only the latest entries."""

		self._ensure_parent()
		serialized = json.dumps(record, ensure_ascii=False)
		with open(self.path, "a+", encoding="utf-8") as handle:
			fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
			try:
				handle.seek(0)
				lines = [line.rstrip("\n") for line in handle if line.strip()]
				lines.append(serialized)
				if len(lines) > self.max_records:
					lines = lines[-self.max_records :]
				handle.seek(0)
				handle.truncate()
				handle.write("\n".join(lines))
				handle.write("\n")
			finally:
				fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

	def read_latest(self, limit: int | None = None) -> List[Dict[str, Any]]:
		"""Return newest-first telemetry entries up to *limit*."""

		if not self.path.exists():
			return []

		with open(self.path, "r", encoding="utf-8") as handle:
			fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
			try:
				records = [json.loads(line) for line in handle if line.strip()]
			finally:
				fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

		if not records:
			return []

		recent = records[-(limit or len(records)) :]
		return list(reversed(recent))


telemetry_store = TelemetryStore(
	path=settings.TELEMETRY_FILE_PATH,
	max_records=settings.TELEMETRY_MAX_RECORDS,
)

__all__ = ["TelemetryStore", "telemetry_store"]
