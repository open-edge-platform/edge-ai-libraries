"""SQLAlchemy ORM models for the benchmark database schema."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Metadata(Base):
    """Singleton table; id is always 1."""

    __tablename__ = "metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    db_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)


class BenchmarkSuite(Base):
    """Top-level benchmark suite definition."""

    __tablename__ = "benchmark_suites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class BenchmarkWorkload(Base):
    """Pipeline workload definition within a benchmark suite."""

    __tablename__ = "benchmark_workloads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_id: Mapped[str] = mapped_column(String(255), nullable=False)
    variants: Mapped[str] = mapped_column(String(255), nullable=False)


class BenchmarkTestCase(Base):
    """Concrete test case for a workload."""

    __tablename__ = "benchmark_test_cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workload_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_workloads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    streams: Mapped[int] = mapped_column(Integer, nullable=False)


class BenchmarkSuiteRun(Base):
    """Execution record for an entire benchmark suite."""

    __tablename__ = "benchmark_suite_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    suite_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_performance: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    execution_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    total_test_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_test_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BenchmarkWorkloadRun(Base):
    """Execution record for one workload within a suite run."""

    __tablename__ = "benchmark_workload_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workload_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_workloads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    suite_run_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_suite_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_performance: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    execution_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    total_test_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_test_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BenchmarkTestCaseRun(Base):
    """Execution record for one test case run."""

    __tablename__ = "benchmark_test_case_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_test_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workload_run_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_workload_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    execution_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_stream_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    npu_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    media_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_performance: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")


class Model(Base):
    """Canonical model catalog entry, seeded from vippet/models/*.yaml.

    ``install_status`` and ``installed_at`` are denormalized/code-managed:
    set explicitly by the download/upload completion handlers (or by the
    one-time disk backfill run when this table is first populated), never
    recomputed from a live filesystem scan.
    """

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    hub: Mapped[str] = mapped_column(String(50), nullable=False)
    unsupported_devices: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    install_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_installed"
    )
    installed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    download_request: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ModelVariant(Base):
    """One (precision, model-proc) combination of a catalog `Model`.

    ``name`` mirrors the legacy ``SupportedModel.name`` and is only
    unique per (precision, model_proc): when a canonical model has no
    ``model_proc``/``extra_model_procs`` aliases, every precision of
    that model shares the same ``name`` (only ``display_name`` differs
    per precision) - so uniqueness is enforced on
    ``(model_id, precision, model_proc)``, not on ``name`` alone.

    ``installed`` is set directly by the download/upload completion
    handler (or the one-time disk backfill), never via a live disk scan.
    """

    __tablename__ = "model_variants"
    __table_args__ = (
        UniqueConstraint(
            "model_id", "precision", "model_proc", name="uq_model_variant_key"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    precision: Mapped[str] = mapped_column(String(20), nullable=False)
    model_path: Mapped[str] = mapped_column(String(500), nullable=False)
    model_proc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    installed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    installed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
