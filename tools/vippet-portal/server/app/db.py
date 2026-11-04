"""Database engine, session factory and ORM models for the portal."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Instance(Base):
    """A registered ViPPET instance that the portal aggregates results from."""

    __tablename__ = "instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(512), unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cached platform identity, refreshed from /devices on every reachable poll.
    cpu: Mapped[str | None] = mapped_column(String(256), nullable=True)
    gpu: Mapped[str | None] = mapped_column(String(256), nullable=True)
    npu: Mapped[str | None] = mapped_column(String(256), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Experiment(Base):
    """A benchmark suite the portal launched on one or more machines at once."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    suite_slug: Mapped[str] = mapped_column(String(128))
    suite_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ExperimentRun(Base):
    """One machine taking part in an experiment, plus the job it was given."""

    __tablename__ = "experiment_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    instance_id: Mapped[int] = mapped_column(ForeignKey("instances.id", ondelete="CASCADE"))
    #: None when the machine refused or was unreachable at launch time.
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TestExperiment(Base):
    """A performance or density test the portal launched on several machines."""

    __tablename__ = "test_experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    pipeline_id: Mapped[str] = mapped_column(String(256))
    variant_id: Mapped[str] = mapped_column(String(256))
    label: Mapped[str] = mapped_column(String(512))
    #: Performance only: parallel streams per machine.
    streams: Mapped[int | None] = mapped_column(nullable=True)
    #: Seconds per run (one iteration for density), 0 means run to end of stream.
    max_runtime: Mapped[int | None] = mapped_column(nullable=True)
    #: Density only: minimum acceptable per-stream FPS.
    fps_floor: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TestExperimentRun(Base):
    """One machine taking part in a test experiment."""

    __tablename__ = "test_experiment_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("test_experiments.id", ondelete="CASCADE"), index=True
    )
    instance_id: Mapped[int] = mapped_column(ForeignKey("instances.id", ondelete="CASCADE"))
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        existing = set((await session.scalars(select(Instance.url))).all())
        for name, url in settings.seed_instances:
            url = url.rstrip("/")
            if not url or url in existing:
                continue
            session.add(Instance(name=name or url, url=url))
        await session.commit()
