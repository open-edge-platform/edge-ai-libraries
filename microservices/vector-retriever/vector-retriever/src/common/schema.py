# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import get_args
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Guardrail for user-provided metadata field names.
FILTER_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_/\\-]{1,128}$")

# Legacy `filters` map limit; kept for backward-compatible request shape.
MAX_FILTER_FIELDS = 20

# Maximum nesting depth for `where` logical trees.
# Used by `QueryRequest.validate_where_limits()` to block deeply nested
# expressions that are hard to reason about and expensive to evaluate.
MAX_WHERE_DEPTH = 5

# Maximum total number of clauses allowed in a `where` tree.
# Used by `QueryRequest.validate_where_limits()` to prevent oversized
# filter payloads from causing unnecessary CPU and memory pressure.
MAX_WHERE_CLAUSES = 50

# Maximum number of values allowed for list-based operators (`in`,
# `contains_any`, `contains_all`). Enforced in `WhereClause` predicate
# validation to avoid pathological list scans and payload bloat.
MAX_WHERE_LIST_SIZE = 100


FilterOperator = Literal[
    "eq",
    "in",
    "contains",
    "starts_with",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "contains_any",
    "contains_all",
    "exists",
    "missing",
]

# Single source of truth for supported operators is `FilterOperator`.
FILTER_OPERATORS: tuple[str, ...] = tuple(get_args(FilterOperator))

# Logical blocks supported by `where` grammar.
FILTER_LOGICAL_BLOCKS: tuple[str, ...] = ("all", "any", "not")


class TimeRange(BaseModel):
    """Inclusive timestamp window used by time-based filtering."""

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_window(self) -> "TimeRange":
        """Ensure the time window starts before or at the end timestamp."""
        if self.start > self.end:
            raise ValueError("time_filter.start must be less than or equal to time_filter.end")
        return self


def _parse_timezone_aware_datetime(value: Any) -> datetime | None:
    """Return timezone-aware datetime when input is an ISO string, else None."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime values must include timezone information")
        return value
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime values must include timezone information")
    return parsed


class WhereClause(BaseModel):
    """Primary recursive filter grammar used across all backends.

    A clause is either:
    1) an atomic predicate: `field` + `op` + `value`, or
    2) one logical block: `all`, `any`, or `not`.
    """

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    field: str | None = None
    op: FilterOperator | None = None
    value: Any | None = None
    all: list["WhereClause"] | None = None
    any: list["WhereClause"] | None = None
    not_: "WhereClause | None" = Field(default=None, alias="not")

    _TEXT_OPERATORS: ClassVar[set[str]] = {"contains", "starts_with"}
    _RANGE_OPERATORS: ClassVar[set[str]] = {"gt", "gte", "lt", "lte", "between"}
    _LIST_OPERATORS: ClassVar[set[str]] = {"in", "contains_any", "contains_all"}

    @model_validator(mode="after")
    def validate_clause_shape(self) -> "WhereClause":
        """Enforce grammar shape so query behavior remains deterministic."""
        has_predicate = self.field is not None or self.op is not None or self.value is not None
        logical_keys = [
            self.all is not None,
            self.any is not None,
            self.not_ is not None,
        ]
        logical_count = sum(logical_keys)

        if has_predicate and logical_count > 0:
            raise ValueError("where clause cannot mix predicate fields with logical blocks")

        if has_predicate:
            if not self.field or not self.field.strip():
                raise ValueError("where predicate must include a non-empty field")
            if not FILTER_FIELD_NAME_PATTERN.match(self.field):
                raise ValueError("where.field must match ^[A-Za-z0-9_/\\-]{1,128}$")
            if self.op is None:
                raise ValueError("where predicate must include op")
            self._validate_predicate_value()
            return self

        if logical_count != 1:
            raise ValueError("where clause must define exactly one of all, any, not, or a predicate")

        if self.all is not None and not self.all:
            raise ValueError("where.all must include at least one clause")
        if self.any is not None and not self.any:
            raise ValueError("where.any must include at least one clause")

        return self

    def _validate_predicate_value(self) -> None:
        """Validate operator/value compatibility for predictable semantics."""
        assert self.op is not None

        if self.op in {"exists", "missing"}:
            if self.value is not None:
                raise ValueError(f"where.value must be omitted when op='{self.op}'")
            return

        if self.value is None:
            raise ValueError(f"where.value is required when op='{self.op}'")

        if self.op in self._LIST_OPERATORS:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError(
                    f"where.value must be a non-empty list when op='{self.op}'"
                )
            if len(self.value) > MAX_WHERE_LIST_SIZE:
                raise ValueError(
                    f"where.value list cannot exceed {MAX_WHERE_LIST_SIZE} entries"
                )
            return

        if self.op == "between":
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError("where.value must be a list of length 2 when op='between'")
            self._validate_datetime_values(self.value)
            return

        if self.op in self._TEXT_OPERATORS and not isinstance(self.value, str):
            raise ValueError(f"where.value must be a string when op='{self.op}'")

        if self.op in self._RANGE_OPERATORS:
            self._validate_datetime_values([self.value])

    @staticmethod
    def _validate_datetime_values(values: list[Any]) -> None:
        """Require timezone when values look like datetimes.

        This avoids ambiguous local-time comparisons across services.
        """
        for item in values:
            try:
                _parse_timezone_aware_datetime(item)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
            except Exception:
                # Non-datetime values are allowed for numeric ranges.
                continue

    def clause_count(self) -> int:
        """Return recursive clause count for safety limits."""
        if self.all is not None:
            return 1 + sum(item.clause_count() for item in self.all)
        if self.any is not None:
            return 1 + sum(item.clause_count() for item in self.any)
        if self.not_ is not None:
            return 1 + self.not_.clause_count()
        return 1

    def max_depth(self) -> int:
        """Return maximum nesting depth for safety limits."""
        if self.all is not None:
            return 1 + max(item.max_depth() for item in self.all)
        if self.any is not None:
            return 1 + max(item.max_depth() for item in self.any)
        if self.not_ is not None:
            return 1 + self.not_.max_depth()
        return 1


WhereClause.model_rebuild()


class ImageUrlInput(BaseModel):
    """Image query input provided as a URL."""

    type: Literal["image_url"]
    image_url: str = Field(min_length=1)


class ImageBase64Input(BaseModel):
    """Image query input provided as base64-encoded data."""

    type: Literal["image_base64"]
    image_base64: str = Field(min_length=1)


ImageInput = ImageUrlInput | ImageBase64Input
"""Discriminated union for image query inputs (URL or base64)."""


class QueryRequest(BaseModel):
    """Single retrieval query payload accepted by the batch API.

    Exactly one of ``query`` (text) or ``image`` must be provided.
    """

    query_id: str | None = None
    query: str | None = Field(default=None, min_length=1)
    image: ImageInput | None = Field(default=None, discriminator="type")
    tags: list[str] | None = None
    time_filter: TimeRange | None = None
    filters: dict[str, "FilterCondition"] | None = None
    where: WhereClause | None = None
    top_k: int | None = None
    explain_filters: bool = False

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str | None) -> str | None:
        """Normalize and validate the query text value."""
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query must be a non-empty string")
        return cleaned

    @model_validator(mode="after")
    def validate_query_modality(self) -> "QueryRequest":
        """Enforce that exactly one of query (text) or image is provided."""
        has_text = self.query is not None
        has_image = self.image is not None
        if has_text and has_image:
            raise ValueError("query and image are mutually exclusive; provide exactly one")
        if not has_text and not has_image:
            raise ValueError("either query (text) or image must be provided")
        return self

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        """Trim tag values and drop empty entries."""
        if value is None:
            return value
        normalized = [tag.strip() for tag in value if tag and tag.strip()]
        return normalized or None

    @field_validator("filters")
    @classmethod
    def validate_filter_keys(
        cls, value: dict[str, "FilterCondition"] | None
    ) -> dict[str, "FilterCondition"] | None:
        """Validate dynamic filter keys against length and character rules."""
        if value is None:
            return value
        if len(value) > MAX_FILTER_FIELDS:
            raise ValueError(f"filters cannot contain more than {MAX_FILTER_FIELDS} fields")
        for key in value.keys():
            if not key or not key.strip():
                raise ValueError("filters cannot contain empty field names")
            if not FILTER_FIELD_NAME_PATTERN.match(key):
                raise ValueError(
                    "filter field names must match ^[A-Za-z0-9_/\\-]{1,128}$"
                )
        return value

    @model_validator(mode="after")
    def validate_where_limits(self) -> "QueryRequest":
        """Enforce depth and clause limits for `where` filter trees."""
        if self.where is None:
            return self
        clause_count = self.where.clause_count()
        max_depth = self.where.max_depth()
        if clause_count > MAX_WHERE_CLAUSES:
            raise ValueError(f"where cannot contain more than {MAX_WHERE_CLAUSES} clauses")
        if max_depth > MAX_WHERE_DEPTH:
            raise ValueError(f"where depth cannot exceed {MAX_WHERE_DEPTH}")
        return self


class FilterCondition(BaseModel):
    """Typed operator/value representation for legacy `filters` map.

    This model remains to support backward compatibility while `where`
    is the preferred request shape.
    """

    op: Literal["eq", "in", "gte", "lte", "between"]
    value: Any

    @model_validator(mode="after")
    def validate_by_op(self) -> "FilterCondition":
        """Enforce operator-specific value constraints."""
        if self.op == "in" and not isinstance(self.value, list):
            raise ValueError("filters.<field>.value must be a list when op='in'")
        if self.op == "between":
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError(
                    "filters.<field>.value must be a list of length 2 when op='between'"
                )
        return self


class QueryResultItem(BaseModel):
    """Single scored document returned by vector similarity search."""

    score: float
    metadata: dict[str, Any]
    page_content: str


class AppliedFilters(BaseModel):
    """Echo of filters applied while serving a query.

    - `normalized_where`: primary interpreted filter tree.
    - `warnings`: normalization or pushdown notes.
    - `compiled_backend_filter`: backend-native payload when explain is enabled.
    - `dropped_or_rewritten_clauses`: transparency for rewritten or fallback-only clauses.
    """

    tags: list[str] | None = None
    time_filter: TimeRange | None = None
    filters: dict[str, FilterCondition] | None = None
    normalized_where: WhereClause | None = None
    warnings: list[str] | None = None
    compiled_backend_filter: dict[str, Any] | str | None = None
    dropped_or_rewritten_clauses: list[str] | None = None


class BackendFilterCapabilities(BaseModel):
    """Per-backend filter capabilities for UI discovery and validation."""

    backend: str
    top_level_fields: list[str]
    logical_blocks: list[str]
    supported_operators: list[str]
    pushdown_operators: list[str]
    known_fields: dict[str, str]
    max_where_depth: int
    max_where_clauses: int
    max_where_list_size: int


class FilterCapabilitiesResponse(BaseModel):
    """Top-level response model for filter capability discovery endpoint."""

    active_backend: str
    backends: list[BackendFilterCapabilities]


class QueryResultBlock(BaseModel):
    """Per-query result block included in batch responses."""

    query_id: str
    query: str
    count: int
    items: list[QueryResultItem]
    applied_filters: AppliedFilters


class QueryError(BaseModel):
    """Per-query error information for partial failures in a batch."""

    query_id: str | None = None
    code: str
    message: str


class BatchQueryResponse(BaseModel):
    """Top-level response payload for a batch query request."""

    request_id: str
    results: list[QueryResultBlock]
    errors: list[QueryError]


class HealthResponse(BaseModel):
    """Simple health/readiness response model."""

    status: str
    timestamp: str
