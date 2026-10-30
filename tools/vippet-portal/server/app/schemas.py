"""Pydantic schemas exposed by the portal API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import ConfigDict, Field, field_validator


class TestKind(StrEnum):
    performance = "performance"
    density = "density"


class BaseModel(_PydanticBaseModel):
    # Responses always include defaulted fields, so the generated UI types must not mark them optional.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class InstanceCreate(BaseModel):
    url: str
    name: str | None = None
    notes: str | None = None

    @field_validator("url")
    @classmethod
    def normalise_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            raise ValueError("url must not be empty")
        if not value.startswith(("http://", "https://")):
            value = f"http://{value}"
        return value


class InstanceUpdate(BaseModel):
    url: str | None = None
    name: str | None = None
    notes: str | None = None
    enabled: bool | None = None

    @field_validator("url")
    @classmethod
    def normalise_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return InstanceCreate.normalise_url(value)


class Instance(BaseModel):
    id: int
    name: str
    url: str
    enabled: bool
    notes: str | None = None
    cpu: str | None = None
    gpu: str | None = None
    npu: str | None = None
    version: str | None = None


class InstanceHealth(Instance):
    reachable: bool = False
    ready: bool = False
    status: str | None = None
    error: str | None = None
    benchmark_run_count: int = 0
    performance_job_count: int = 0
    density_job_count: int = 0
    best_score: float | None = None
    last_run_time: int | None = None


class InstanceRef(BaseModel):
    """Identifies which machine a result came from."""

    instance_id: int
    instance_name: str
    instance_url: str
    cpu: str | None = None


class BenchmarkRun(InstanceRef):
    id: int
    suite_slug: str
    suite_name: str | None = None
    status: str
    score_total: float | None = None
    score_performance: float | None = None
    score_efficiency: float | None = None
    start_time: int
    execution_time: int | None = None
    total_test_cases: int | None = None
    passed_test_cases: int | None = None
    #: Stable portal-wide identifier: "<instance_id>:<suite_slug>:<run_id>".
    ref: str


class TestJob(InstanceRef):
    id: str
    kind: TestKind
    state: str
    start_time: int | None = None
    elapsed_time: int | None = None
    total_fps: float | None = None
    per_stream_fps: float | None = None
    total_streams: int | None = None
    details: list[str] = Field(default_factory=list)
    workload: str | None = None
    pipelines: list[str] = Field(default_factory=list)
    #: Stable portal-wide identifier: "<instance_id>:<job_id>".
    ref: str


class BenchmarkSuite(BaseModel):
    """A suite offered by at least one machine, usable as an experiment."""

    slug: str
    name: str
    description: str | None = None
    workload_count: int = 0
    #: Machines that currently expose this suite.
    instance_ids: list[int] = Field(default_factory=list)


class ExperimentCreate(BaseModel):
    suite_slug: str
    instance_ids: list[int] = Field(min_length=1)


class ExperimentRun(BaseModel):
    """One machine's participation in an experiment."""

    instance_id: int
    instance_name: str
    cpu: str | None = None
    job_id: str | None = None
    state: str
    error: str | None = None
    start_time: int | None = None
    elapsed_time: int | None = None
    total_test_cases: int | None = None
    completed_test_cases: int | None = None
    score_total: float | None = None
    score_performance: float | None = None
    score_efficiency: float | None = None
    #: Benchmark run ref, available once the suite run exists upstream.
    ref: str | None = None


class Experiment(BaseModel):
    id: int
    suite_slug: str
    suite_name: str | None = None
    created_at: datetime
    state: str
    runs: list[ExperimentRun] = Field(default_factory=list)


class PipelineVariant(BaseModel):
    id: str
    name: str


class Pipeline(BaseModel):
    """A pipeline offered by at least one machine, usable as a test workload."""

    id: str
    name: str
    variants: list[PipelineVariant] = Field(default_factory=list)
    instance_ids: list[int] = Field(default_factory=list)


class TestExperimentCreate(BaseModel):
    pipeline_id: str
    variant_id: str
    instance_ids: list[int] = Field(min_length=1)
    #: Performance only.
    streams: int = Field(default=1, ge=1)
    #: Seconds per pipeline run; for density this is the duration of one iteration.
    max_runtime: int = Field(default=0, ge=0)
    #: Density only.
    fps_floor: int = Field(default=30, ge=1)


class TestExperimentRun(BaseModel):
    instance_id: int
    instance_name: str
    cpu: str | None = None
    job_id: str | None = None
    state: str
    error: str | None = None
    start_time: int | None = None
    elapsed_time: int | None = None
    total_fps: float | None = None
    per_stream_fps: float | None = None
    total_streams: int | None = None
    #: Job ref, usable with the test comparison endpoint.
    ref: str | None = None


class TestExperiment(BaseModel):
    id: int
    kind: TestKind
    pipeline_id: str
    variant_id: str
    label: str
    streams: int | None = None
    max_runtime: int | None = None
    fps_floor: int | None = None
    created_at: datetime
    state: str
    runs: list[TestExperimentRun] = Field(default_factory=list)


class ComparisonColumn(BaseModel):
    """One compared result (a benchmark run or a single test job)."""

    ref: str
    label: str
    instance_id: int
    instance_name: str
    cpu: str | None = None
    status: str | None = None
    start_time: int | None = None
    summary: dict[str, float | None] = Field(default_factory=dict)


class ComparisonRow(BaseModel):
    """One comparable workload, aligned across every compared column."""

    key: str
    label: str
    group: str | None = None
    cells: dict[str, dict[str, Any]] = Field(default_factory=dict)


class Comparison(BaseModel):
    columns: list[ComparisonColumn]
    rows: list[ComparisonRow]
    metrics: list[str]
    errors: dict[str, str] = Field(default_factory=dict)
