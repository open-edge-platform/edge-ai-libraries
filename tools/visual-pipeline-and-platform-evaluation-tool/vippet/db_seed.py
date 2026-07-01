"""Database seed data loaded during application startup."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orm_models import Benchmark, BenchmarkPerformanceSetup, BenchmarkType

logger = logging.getLogger(__name__)


async def seed_initial_data(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """
    Insert initial rows in an idempotent way.

    Seeding runs on startup after schema creation.
    """
    async with session_maker() as session:
        benchmark_specs = [
            {
                "name": "Smart Parking CPU",
                "type": BenchmarkType.performance,
                "setups": [
                    {
                        "pipeline_id": "smart-parking",
                        "variant_id": "cpu",
                        "streams": 8,
                    }
                ],
            },
            {
                "name": "NVR GPU",
                "type": BenchmarkType.performance,
                "setups": [
                    {
                        "pipeline_id": "smart-nvr",
                        "variant_id": "gpu",
                        "streams": 4,
                    },
                    {
                        "pipeline_id": "simple-nvr",
                        "variant_id": "gpu",
                        "streams": 8,
                    },
                ],
            },
        ]

        for benchmark_spec in benchmark_specs:
            benchmark = await session.scalar(
                select(Benchmark).where(Benchmark.name == benchmark_spec["name"])
            )

            if benchmark is None:
                benchmark = Benchmark(
                    name=benchmark_spec["name"],
                    type=benchmark_spec["type"],
                )
                session.add(benchmark)
                await session.flush()

            for setup in benchmark_spec["setups"]:
                existing_setup = await session.scalar(
                    select(BenchmarkPerformanceSetup).where(
                        BenchmarkPerformanceSetup.benchmark_id == benchmark.id,
                        BenchmarkPerformanceSetup.pipeline_id == setup["pipeline_id"],
                        BenchmarkPerformanceSetup.variant_id == setup["variant_id"],
                    )
                )
                if existing_setup is None:
                    session.add(
                        BenchmarkPerformanceSetup(
                            benchmark_id=benchmark.id,
                            pipeline_id=setup["pipeline_id"],
                            variant_id=setup["variant_id"],
                            streams=setup["streams"],
                        )
                    )

        await session.commit()
        logger.info("Database seed ensured startup benchmark data")
