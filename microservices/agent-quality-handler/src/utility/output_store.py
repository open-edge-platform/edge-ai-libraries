# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Atomic JSON history for terminal per-agent outputs."""

import json
import os
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.routing.agent_registry import AgentSpec, DEFAULT_REGISTRY


# The REST/storage surface exposes ``ticket`` while the built-in registry and
# execution graph use the agent name ``ticketing``. Preserve that legacy file
# name and API key for backward compatibility with existing on-disk history.
_LEGACY_STORAGE_AGENT_NAMES = {"ticketing": "ticket"}
_LEGACY_RESULT_KEYS = {
    "policy": "policy",
    "analysis": "analysis",
    "evidence": "evidence",
    "ticketing": "ticket",
}


def agent_result_keys(
    specs: list[AgentSpec] | tuple[AgentSpec, ...] | None = None,
) -> dict[str, tuple[str, str]]:
    """Return output-store keys derived from the configured agent registry.

    The mapping shape stays backward-compatible:

    ``{storage_agent_name: (pipeline_result_key, execution_agent_name)}``

    For the built-in ticketing agent this deliberately remains
    ``{"ticket": ("ticket", "ticketing")}``, preserving the long-standing
    ``ticket.json`` file and ``/agents/outputs/ticket`` API contract.
    """
    resolved_specs = DEFAULT_REGISTRY if specs is None else tuple(specs)
    keys: dict[str, tuple[str, str]] = {}

    for spec in resolved_specs:
        storage_agent = _LEGACY_STORAGE_AGENT_NAMES.get(spec.name, spec.name)
        result_key = _LEGACY_RESULT_KEYS.get(spec.name, spec.name)
        if storage_agent in keys:
            raise ValueError(
                f"Duplicate output-store agent key '{storage_agent}' derived from registry"
            )
        keys[storage_agent] = (result_key, spec.name)
    return keys


def _agent_keys(
    specs: list[AgentSpec] | tuple[AgentSpec, ...] | None = None,
) -> tuple[str, ...]:
    """Return the per-agent output document names derived from the registry."""
    return tuple(agent_result_keys(specs))


AGENT_RESULT_KEYS = agent_result_keys()


class OutputStoreError(RuntimeError):
    """Raised when persisted agent output cannot be read or written."""


class AgentOutputStore:
    """Maintain one JSON history document per agent."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        specs: list[AgentSpec] | tuple[AgentSpec, ...] | None = None,
    ):
        self.output_dir = Path(output_dir)
        self._agent_result_keys = agent_result_keys(specs)
        self._lock = threading.RLock()

    def ensure_files(self) -> None:
        with self._lock:
            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                for agent in self._agent_result_keys:
                    path = self._path(agent)
                    if not path.exists():
                        self._write_unlocked(agent, self._empty_document(agent))
                    else:
                        self._read_unlocked(agent)
            except OutputStoreError:
                raise
            except OSError as exc:
                raise OutputStoreError(
                    f"Cannot initialize output directory {self.output_dir}"
                ) from exc

    def record_run(
        self,
        run_id: str,
        *,
        status: str,
        result: dict[str, Any],
        source: str,
        min_id: int | None,
        max_id: int | None,
        metadata: dict[str, Any],
        completed_at: float | None = None,
    ) -> None:
        completed_at = time.time() if completed_at is None else completed_at
        completed_at_iso = datetime.fromtimestamp(
            completed_at, tz=timezone.utc
        ).isoformat()
        run_errors = result.get("errors", [])
        if not isinstance(run_errors, list):
            raise OutputStoreError("Pipeline result errors must be a JSON array")

        with self._lock:
            self.ensure_files()
            documents = {
                agent: self._read_unlocked(agent)
                for agent in self._agent_result_keys
            }
            for agent, (result_key, error_agent) in self._agent_result_keys.items():
                output = self._output_for_agent(result, result_key, error_agent)
                errors = [
                    deepcopy(error)
                    for error in run_errors
                    if isinstance(error, dict) and error.get("agent") == error_agent
                ]
                record = {
                    "run_id": run_id,
                    "run_status": status,
                    "source": source,
                    "min_id": min_id,
                    "max_id": max_id,
                    "completed_at": completed_at,
                    "completed_at_iso": completed_at_iso,
                    "batch_metadata": deepcopy(metadata),
                    "output": deepcopy(output),
                    "errors": errors,
                    "run_errors": deepcopy(run_errors),
                }
                documents[agent]["runs"][run_id] = record

            for agent, document in documents.items():
                self._write_unlocked(agent, document)

    def get_agent(self, agent: str) -> dict[str, Any]:
        self._validate_agent(agent)
        with self._lock:
            self.ensure_files()
            return deepcopy(self._read_unlocked(agent))

    def get_run(self, agent: str, run_id: str) -> dict[str, Any] | None:
        document = self.get_agent(agent)
        record = document["runs"].get(run_id)
        return deepcopy(record) if record is not None else None

    def prune(self, retention_seconds: int, max_runs: int) -> set[str]:
        """Remove expired/excess run IDs from every agent document."""
        with self._lock:
            self.ensure_files()
            documents = {
                agent: self._read_unlocked(agent)
                for agent in self._agent_result_keys
            }
            timestamps: dict[str, float] = {}
            for document in documents.values():
                for run_id, record in document["runs"].items():
                    completed_at = record.get("completed_at")
                    if isinstance(completed_at, (int, float)):
                        timestamps[run_id] = max(
                            timestamps.get(run_id, float("-inf")),
                            float(completed_at),
                        )

            remove: set[str] = set()
            now = time.time()
            if retention_seconds >= 0:
                remove.update(
                    run_id
                    for run_id, completed_at in timestamps.items()
                    if now - completed_at >= retention_seconds
                )
            retained = sorted(
                (
                    (completed_at, run_id)
                    for run_id, completed_at in timestamps.items()
                    if run_id not in remove
                ),
                reverse=True,
            )
            if len(retained) > max_runs:
                remove.update(run_id for _, run_id in retained[max_runs:])

            if remove:
                for agent, document in documents.items():
                    for run_id in remove:
                        document["runs"].pop(run_id, None)
                    self._write_unlocked(agent, document)
            return remove

    def _path(self, agent: str) -> Path:
        return self.output_dir / f"{agent}.json"

    @staticmethod
    def _empty_document(agent: str) -> dict[str, Any]:
        return {"schema_version": "1.0", "agent": agent, "runs": {}}

    def _validate_agent(self, agent: str) -> None:
        if agent not in self._agent_result_keys:
            raise ValueError(f"Unknown agent: {agent}")

    @staticmethod
    def _output_for_agent(
        result: dict[str, Any], result_key: str, execution_agent: str
    ) -> Any:
        if execution_agent not in _LEGACY_RESULT_KEYS:
            extra_agents = result.get("extra_agents")
            if isinstance(extra_agents, dict) and execution_agent in extra_agents:
                return deepcopy(extra_agents[execution_agent])
        return deepcopy(result.get(result_key, {}))

    def _read_unlocked(self, agent: str) -> dict[str, Any]:
        path = self._path(agent)
        try:
            with path.open(encoding="utf-8") as output_file:
                document = json.load(output_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise OutputStoreError(f"Cannot read agent output file {path}") from exc
        if (
            not isinstance(document, dict)
            or document.get("schema_version") != "1.0"
            or document.get("agent") != agent
            or not isinstance(document.get("runs"), dict)
        ):
            raise OutputStoreError(f"Agent output file has invalid schema: {path}")
        return document

    def _write_unlocked(self, agent: str, document: dict[str, Any]) -> None:
        path = self._path(agent)
        temporary = self.output_dir / f".{agent}.{uuid.uuid4().hex}.tmp"
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as output_file:
                json.dump(
                    document,
                    output_file,
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                )
                output_file.write("\n")
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(temporary, path)
        except (OSError, TypeError, ValueError) as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise OutputStoreError(f"Cannot write agent output file {path}") from exc
