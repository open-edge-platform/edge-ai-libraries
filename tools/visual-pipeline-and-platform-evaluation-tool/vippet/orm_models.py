"""
SQLAlchemy ORM models for ViPPET database schema.

Define table structure here by creating classes that inherit from Base.
All models imported by this module are loaded during startup before
Base.metadata.create_all() is executed.

Example:
    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column

    from database import Base

    class JobRecord(Base):
        __tablename__ = "job_records"

        id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        job_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
"""

import enum

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class BenchmarkType(enum.Enum):
    performance = "performance"
    density = "density"


class Benchmark(Base):
    """Benchmark execution record."""

    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[BenchmarkType] = mapped_column(Enum(BenchmarkType), nullable=False)


class BenchmarkPerformanceSetup(Base):
    """Performance test configuration linked to a Benchmark."""

    __tablename__ = "benchmark_performance_setups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    benchmark_id: Mapped[int] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_id: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    streams: Mapped[int] = mapped_column(Integer, nullable=False)


class BenchmarkDensitySetup(Base):
    """Density test configuration linked to a Benchmark."""

    __tablename__ = "benchmark_density_setups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    benchmark_id: Mapped[int] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_id: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    participation_rate: Mapped[float] = mapped_column(nullable=False)


class BenchmarkRun(Base):
    """A single execution run of a Benchmark."""

    __tablename__ = "benchmark_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    benchmark_id: Mapped[int] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    start_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    execution_time: Mapped[int] = mapped_column(BigInteger, nullable=False)


class BenchmarkRunPerformanceSetup(Base):
    """Performance pipeline configuration for a specific BenchmarkRun."""

    __tablename__ = "benchmark_run_performance_setups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    benchmark_run_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_id: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    streams: Mapped[int] = mapped_column(Integer, nullable=False)


class BenchmarkRunDensitySetup(Base):
    """Density pipeline configuration for a specific BenchmarkRun."""

    __tablename__ = "benchmark_run_density_setups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    benchmark_run_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_id: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    participation_rate: Mapped[float] = mapped_column(nullable=False)


class BenchmarkResultPerformance(Base):
    """Aggregated performance result for a BenchmarkRun."""

    __tablename__ = "benchmark_result_performances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    benchmark_id: Mapped[int] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    benchmark_run_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_fps: Mapped[float] = mapped_column(nullable=False)

class BenchmarkResultDensity(Base):
    """Aggregated density result for a BenchmarkRun."""

    __tablename__ = "benchmark_result_densities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    benchmark_id: Mapped[int] = mapped_column(
        ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    benchmark_run_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    per_stream_fps: Mapped[float] = mapped_column(nullable=False)
    stream_distribution_id: Mapped[int] = mapped_column(
        ForeignKey("benchmark_result_density_stream_distributions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

class BenchmarkResultDensityStreamDistribution(Base):
    """Stream distribution across pipelines for a density result."""

    __tablename__ = "benchmark_result_density_stream_distributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    streams: Mapped[int] = mapped_column(Integer, primary_key=True)
