# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Data models for metrics ingestion.

Supports multiple input formats compatible with OpenTelemetry and Telegraf:
- JSON metrics format
- InfluxDB Line Protocol format
- OpenTelemetry metrics format
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .logging_config import get_logger
from .settings import get_settings

_logger = get_logger("models")


class MetricType(StrEnum):
    """Metric type enumeration."""

    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class Metric(BaseModel):
    """
    Single metric data point.

    This format is compatible with Telegraf JSON format and can be converted
    to OpenTelemetry metrics.

    Attributes:
        name: Metric measurement name (e.g., "cpu", "memory", "custom_fps")
        fields: Key-value pairs of metric values (e.g., {"usage": 45.2, "count": 10})
        tags: Optional key-value pairs for metric labels (e.g., {"host": "server1"})
        timestamp: Unix timestamp in seconds or nanoseconds (auto-detected)
        metric_type: Type of metric (gauge, counter, etc.)
    """

    name: str = Field(..., min_length=1, max_length=256, description="Metric name")
    fields: dict[str, int | float | str | bool] = Field(
        ..., min_length=1, description="Metric field values (at least one required)"
    )
    tags: dict[str, str] | None = Field(
        default_factory=dict, description="Metric tags/labels"
    )
    timestamp: int | None = Field(
        default_factory=lambda: int(datetime.now(UTC).timestamp() * 1e9),
        description="Unix timestamp (seconds or nanoseconds)",
    )
    metric_type: MetricType = Field(
        default=MetricType.GAUGE, description="Type of metric"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, v: int | float | str | None) -> int | None:
        """Normalize timestamp to nanoseconds."""
        if v is None:
            return int(datetime.now(UTC).timestamp() * 1e9)
        if isinstance(v, str):
            v = int(float(v))
        if isinstance(v, float):
            v = int(v)
        # Detect if timestamp is in seconds, milliseconds, or nanoseconds
        # Timestamps < 1e12 are likely seconds, < 1e15 are milliseconds
        if v < 1e12:
            return int(v * 1e9)  # seconds to nanoseconds
        elif v < 1e15:
            return int(v * 1e6)  # milliseconds to nanoseconds
        return v  # already nanoseconds

    @staticmethod
    def _escape_measurement(s: str) -> str:
        return s.replace(",", "\\,").replace(" ", "\\ ")

    @staticmethod
    def _escape_tag(s: str) -> str:
        return s.replace(",", "\\,").replace(" ", "\\ ").replace("=", "\\=")

    @staticmethod
    def _escape_string_field(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def to_influx_line(self) -> str:
        """Convert metric to InfluxDB Line Protocol format.

        Returns:
            String in InfluxDB Line Protocol format
        """
        meas = self._escape_measurement(self.name)
        if self.tags:
            tag_str = ",".join(
                f"{self._escape_tag(k)}={self._escape_tag(v)}"
                for k, v in sorted(self.tags.items())
            )
            measurement_part = f"{meas},{tag_str}"
        else:
            measurement_part = meas

        field_parts = []
        for k, v in self.fields.items():
            ek = self._escape_tag(k)
            if isinstance(v, bool):
                field_parts.append(f"{ek}={str(v).lower()}")
            elif isinstance(v, int):
                field_parts.append(f"{ek}={v}i")
            elif isinstance(v, float):
                field_parts.append(f"{ek}={v}")
            elif isinstance(v, str):
                field_parts.append(f'{ek}="{self._escape_string_field(v)}"')

        parts = [measurement_part, ",".join(field_parts)]
        if self.timestamp:
            parts.append(str(self.timestamp))

        return " ".join(parts)

    def to_telegraf_json(self) -> dict[str, Any]:
        """
        Convert metric to Telegraf JSON format.

        Returns:
            Dictionary in Telegraf JSON format
        """
        ts = (
            self.timestamp // int(1e9)
            if self.timestamp
            else int(datetime.now(UTC).timestamp())
        )
        return {
            "name": self.name,
            "tags": self.tags or {},
            "fields": self.fields,
            "timestamp": ts,
        }


class MetricsBatch(BaseModel):
    """
    Batch of metrics for ingestion.

    Supports submitting multiple metrics in a single request.
    The effective upper limit is controlled by the ``max_metrics_batch_size``
    setting (default 1000, max 10000).
    """

    metrics: list[Metric] = Field(..., min_length=1)

    @model_validator(mode="after")
    def check_batch_size(self) -> "MetricsBatch":
        limit = get_settings().max_metrics_batch_size
        if len(self.metrics) > limit:
            raise ValueError(
                f"Batch size {len(self.metrics)} exceeds the configured limit of {limit}"
            )
        return self

    def to_influx_lines(self) -> str:
        """Convert all metrics to InfluxDB Line Protocol format."""
        return "\n".join(m.to_influx_line() for m in self.metrics)

    def to_telegraf_json(self) -> list[dict[str, Any]]:
        """Convert all metrics to Telegraf JSON format."""
        return [m.to_telegraf_json() for m in self.metrics]


class SimpleMetric(BaseModel):
    """
    Simplified metric format for easy custom metric submission.

    Example:
        {
            "name": "fps",
            "value": 29.97,
            "timestamp": 1776947971
        }

    Timestamp accepts seconds, milliseconds, or nanoseconds (auto-detected).
    """

    name: str = Field(..., min_length=1, max_length=256)
    value: int | float = Field(..., description="Metric value")
    tags: dict[str, str] | None = Field(default_factory=dict)
    timestamp: int | float | None = Field(
        default=None,
        description=(
            "Unix timestamp. Accepts seconds (< 1e12), milliseconds (< 1e15), "
            "or nanoseconds. Defaults to current UTC time if omitted."
        ),
    )

    def to_metric(self) -> Metric:
        """Convert to full Metric object."""
        return Metric(
            name=self.name,
            fields={"value": self.value},
            tags=self.tags,
            timestamp=self.timestamp,
        )


class InfluxLineProtocolInput(BaseModel):
    """
    Parser for InfluxDB Line Protocol format.

    Used exclusively via the static parse_line() method; not instantiated
    from request bodies.
    """

    @staticmethod
    def _split_unescaped(s: str, sep: str) -> list[str]:
        """Split on unescaped occurrences of sep (single char)."""
        parts: list[str] = []
        current: list[str] = []
        i = 0
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                current.append(s[i : i + 2])
                i += 2
            elif s[i] == sep:
                parts.append("".join(current))
                current = []
                i += 1
            else:
                current.append(s[i])
                i += 1
        parts.append("".join(current))
        return parts

    @staticmethod
    def _unescape_tag(s: str) -> str:
        return s.replace("\\,", ",").replace("\\ ", " ").replace("\\=", "=")

    @staticmethod
    def _unescape_string_field(s: str) -> str:
        return s.replace('\\"', '"').replace("\\\\", "\\")

    @classmethod
    def parse_line(cls, line: str) -> Metric | None:
        """
        Parse a single InfluxDB Line Protocol line into a Metric.

        Format: <measurement>[,<tag>=<value>...] <field>=<value>[,...] [timestamp]
        Handles backslash-escaped separators per the InfluxDB LP spec.
        """
        line = line.strip()
        if not line:
            return None

        try:
            # Split on unescaped spaces: [meas+tags, fields, optional timestamp]
            parts = cls._split_unescaped(line, " ")
            if len(parts) < 2:
                return None

            # Parse measurement and tags
            meas_tags = cls._split_unescaped(parts[0], ",")
            name = cls._unescape_tag(meas_tags[0])
            tags: dict = {}
            for tag in meas_tags[1:]:
                if "=" in tag:
                    k, v = tag.split("=", 1)
                    tags[cls._unescape_tag(k)] = cls._unescape_tag(v)

            # Parse fields
            fields: dict = {}
            for field in cls._split_unescaped(parts[1], ","):
                if "=" not in field:
                    continue
                k, v = field.split("=", 1)
                fk = cls._unescape_tag(k)
                if v.endswith("i"):
                    try:
                        fields[fk] = int(v[:-1])
                    except ValueError:
                        pass
                elif v.startswith('"') and v.endswith('"'):
                    fields[fk] = cls._unescape_string_field(v[1:-1])
                elif v.lower() in ("true", "false"):
                    fields[fk] = v.lower() == "true"
                else:
                    try:
                        fields[fk] = float(v)
                    except ValueError:
                        fields[fk] = v

            timestamp = None
            if len(parts) > 2:
                try:
                    timestamp = int(parts[2])
                except ValueError:
                    pass

            return Metric(name=name, fields=fields, tags=tags, timestamp=timestamp)
        except Exception as exc:
            _logger.debug(
                "Failed to parse InfluxDB line",
                extra={"line_preview": line[:80], "error": str(exc)},
            )
            return None


class OpenTelemetryMetric(BaseModel):
    """
    OpenTelemetry-compatible metric format.

    Follows OTLP JSON format for metrics.
    """

    resource_metrics: list[dict[str, Any]] = Field(
        default_factory=list, alias="resourceMetrics"
    )

    def to_metrics(self) -> list[Metric]:
        """
        Convert OpenTelemetry format to internal Metric objects.

        This handles the OTLP JSON format and extracts individual metrics.
        """
        metrics = []
        for rm in self.resource_metrics:
            resource_attrs = {}
            if "resource" in rm and "attributes" in rm["resource"]:
                for attr in rm["resource"]["attributes"]:
                    resource_attrs[attr.get("key", "")] = str(
                        attr.get("value", {}).get("stringValue", "")
                    )

            for sm in rm.get("scopeMetrics", []):
                for m in sm.get("metrics", []):
                    name = m.get("name", "unknown")

                    # Handle different metric types
                    data_points = []
                    if "gauge" in m:
                        data_points = m["gauge"].get("dataPoints", [])
                    elif "sum" in m:
                        data_points = m["sum"].get("dataPoints", [])
                    elif "histogram" in m:
                        data_points = m["histogram"].get("dataPoints", [])

                    for dp in data_points:
                        tags = dict(resource_attrs)
                        for attr in dp.get("attributes", []):
                            tags[attr.get("key", "")] = str(
                                attr.get("value", {}).get("stringValue", "")
                            )

                        as_double = dp.get("asDouble")
                        value = as_double if as_double is not None else dp.get("asInt", 0)
                        timestamp = dp.get("timeUnixNano")

                        metrics.append(
                            Metric(
                                name=name,
                                fields={"value": value},
                                tags=tags,
                                timestamp=timestamp,
                            )
                        )

        return metrics
