# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Parsed probe configuration.

A :class:`ProbeSpec` is the config that *is* the protocol: it declares the
endpoint, tick cadence, what to extract, how to aggregate, and where to publish.
One generic :class:`~src.providers.probes.probe.ProviderProbe` is parameterised
by it — there is no per-backend probe subclass. Specs are parsed once from the
free-form ``settings.probes`` list (see :func:`ProbeSpec.from_mapping`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


# Defaults applied when a spec omits a field.
DEFAULT_INTERVAL = 10.0        # seconds between ticks
DEFAULT_TIMEOUT = 5.0          # per-request timeout — must not stall reporting
DEFAULT_METHOD = "GET"
DEFAULT_WINDOW = 20            # sliding-window size, per discovered series
DEFAULT_METHOD_STAT = "mean"
# Guard against a broad regex creating a runaway number of series.
DEFAULT_MAX_SERIES = 200
# Where a metadata sink writes when the spec omits ``prefix``.
DEFAULT_PREFIX = "attributes.probe"
# Cap on a file sink's JSONL history so a long-running probe can't grow it
# without bound. The sink retains the most recent ``DEFAULT_FILE_MAX_ENTRIES``
# records; set ``max_entries: 0`` on the sink to disable the cap.
DEFAULT_FILE_MAX_ENTRIES = 10000


class ProbeConfigError(ValueError):
    """Raised when a probe spec is malformed."""


@dataclass(frozen=True)
class ExtractRule:
    """One extraction rule: a regex over the response text, or a JSON dot-path.

    - ``regex``: run against the response text; **every** match yields one
      ``(name, value)`` pair where the *last* capture group is the value (cast
      to float) and the group *before* it is the field name.
    - ``json_path``: a ``dot.path`` into the parsed JSON body; the field name is
      the last path segment and the value is the (numeric) leaf.
    """

    regex: Optional[str] = None
    json_path: Optional[str] = None

    def __post_init__(self) -> None:
        if bool(self.regex) == bool(self.json_path):
            raise ProbeConfigError(
                "each extract rule needs exactly one of 'regex' or 'json'"
            )

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ExtractRule":
        return cls(regex=raw.get("regex"), json_path=raw.get("json"))


@dataclass(frozen=True)
class AggregateSpec:
    """Sliding-window aggregation applied independently to each series."""

    window: int = DEFAULT_WINDOW
    method: str = DEFAULT_METHOD_STAT

    @classmethod
    def from_mapping(cls, raw: Optional[dict[str, Any]]) -> "AggregateSpec":
        raw = raw or {}
        window = int(raw.get("window", DEFAULT_WINDOW))
        if window <= 0:
            raise ProbeConfigError(f"aggregate.window must be positive, got {window}")
        return cls(window=window, method=str(raw.get("method", DEFAULT_METHOD_STAT)).lower())


@dataclass(frozen=True)
class PublishSpec:
    """One publish destination (sink)."""

    to: str                       # "metadata" | "file"
    prefix: str = DEFAULT_PREFIX  # metadata: dotted path root, <prefix>.<name>
    path: Optional[str] = None    # file: JSONL path
    # file: keep only the most recent N records (0 → unbounded).
    max_entries: int = DEFAULT_FILE_MAX_ENTRIES


@dataclass(frozen=True)
class ProbeSpec:
    """A single provider probe, fully described by config."""

    name: str
    enabled: bool
    interval: float
    timeout: float
    method: str
    extract: List[ExtractRule]
    aggregate: AggregateSpec
    publish: List[PublishSpec]
    endpoint: Optional[str] = None  # falls back to the provider's endpoint
    max_series: int = DEFAULT_MAX_SERIES

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ProbeSpec":
        """Parse one ``settings.probes[i]`` entry, applying defaults."""
        name = raw.get("name")
        if not name:
            raise ProbeConfigError("probe spec missing required 'name'")

        extract_raw = raw.get("extract") or []
        if not isinstance(extract_raw, list) or not extract_raw:
            raise ProbeConfigError(f"probe '{name}' needs a non-empty 'extract' list")
        extract = [ExtractRule.from_mapping(rule) for rule in extract_raw]

        publish = cls._parse_publish(name, raw.get("publish"))

        return cls(
            name=str(name),
            enabled=bool(raw.get("enabled", True)),
            endpoint=raw.get("endpoint"),
            interval=float(raw.get("interval", DEFAULT_INTERVAL)),
            timeout=float(raw.get("timeout", DEFAULT_TIMEOUT)),
            method=str(raw.get("method", DEFAULT_METHOD)).upper(),
            extract=extract,
            aggregate=AggregateSpec.from_mapping(raw.get("aggregate")),
            publish=publish,
            max_series=int(raw.get("max_series", DEFAULT_MAX_SERIES)),
        )

    @staticmethod
    def _parse_publish(name: str, raw_publish: Any) -> List[PublishSpec]:
        """Expand the ``publish`` list, unfolding ``to: both`` into two sinks."""
        if not raw_publish:
            # A probe with no sink is pointless; default to the live metadata.
            return [PublishSpec(to="metadata", prefix=DEFAULT_PREFIX)]
        if not isinstance(raw_publish, list):
            raise ProbeConfigError(f"probe '{name}' 'publish' must be a list")

        sinks: List[PublishSpec] = []
        for entry in raw_publish:
            to = str(entry.get("to", "")).lower()
            prefix = entry.get("prefix", DEFAULT_PREFIX)
            path = entry.get("path")
            if to in ("metadata", "both"):
                sinks.append(PublishSpec(to="metadata", prefix=prefix))
            if to in ("file", "both"):
                if not path:
                    raise ProbeConfigError(
                        f"probe '{name}' file sink needs a 'path'"
                    )
                max_entries = ProbeSpec._parse_max_entries(name, entry.get("max_entries"))
                sinks.append(PublishSpec(to="file", path=path, max_entries=max_entries))
            if to not in ("metadata", "file", "both"):
                raise ProbeConfigError(
                    f"probe '{name}' has unknown publish target {to!r} "
                    "(expected metadata|file|both)"
                )
        return sinks

    @staticmethod
    def _parse_max_entries(name: str, raw: Any) -> int:
        """Parse a file sink's ``max_entries`` (default ``DEFAULT_FILE_MAX_ENTRIES``).

        ``0`` disables the cap (unbounded history); negative values are rejected.
        """
        if raw is None:
            return DEFAULT_FILE_MAX_ENTRIES
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ProbeConfigError(
                f"probe '{name}' file sink 'max_entries' must be an integer, got {raw!r}"
            )
        if value < 0:
            raise ProbeConfigError(
                f"probe '{name}' file sink 'max_entries' must be >= 0, got {value}"
            )
        return value
