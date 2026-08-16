"""SQLAlchemy ORM models for the benchmark database schema."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
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
