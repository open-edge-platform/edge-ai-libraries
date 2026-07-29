"""Database seed data loaded during application startup."""

from datetime import datetime, timezone
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orm_models import BenchmarkSuite, BenchmarkTestCase, BenchmarkWorkload
from utils import slugify_text

logger = logging.getLogger(__name__)


async def seed_initial_data(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """
    Insert initial rows in an idempotent way.

    Seeding runs on startup after schema creation.
    """
    async with session_maker() as session:
        default_test_cases = [1, 4, 16, 64]
        suite_specs = [
            {
                "name": "Small Suite",
                "description": "Small suite.",
                "workloads": [
                    {
                        "pipeline_id": "age-gender-recognition",
                        "variants": [
                            {"name": "cpu", "test_cases": [3, 10]},
                            {"name": "gpu", "test_cases": [3, 10]},
                        ],
                    },
                    {
                        "pipeline_id": "goods-detection-classification",
                        "variants": [
                            {"name": "cpu", "test_cases": [3, 4]},
                            {"name": "gpu", "test_cases": [5, 6]},
                        ],
                    },
                ]
            },
            {
                "name": "Test Suite",
                "description": "Test suite.",
                "workloads": [
                    {
                        "pipeline_id": "age-gender-recognition",
                        "variants": [
                            {"name": "cpu", "test_cases": [3, 5, 10]},
                            {"name": "gpu", "test_cases": [3, 5, 10]},
                        ],
                    },
                    {
                        "pipeline_id": "goods-detection-classification",
                        "variants": [
                            {"name": "cpu", "test_cases": [3, 5]},
                            {"name": "gpu", "test_cases": [3, 5, 8, 9]},
                        ],
                    },
                    {
                        "pipeline_id": "smart-parking",
                        "variants": [
                            {"name": "cpu", "test_cases": [3, 5, 7, 8, 9]},
                            {"name": "gpu", "test_cases": [3, 5, 8, 9]},

                        ],
                    },
                ]
            },
            {
                "name": "Retail Suite",
                "description": "Retail benchmark suite covering retail analytics pipelines.",
                "workloads": [
                    {
                        "pipeline_id": "age-gender-recognition",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                            {"name": "npu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "goods-detection",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                            {"name": "npu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "goods-detection-classification",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                            {"name": "npu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "segmentation",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                        ],
                    }
                ],
            },
            {
                "name": "Metro Suite",
                "description": "Metro benchmark suite covering city and transport analytics pipelines.",
                "workloads": [
                    {
                        "pipeline_id": "smart-nvr",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                            {"name": "npu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "simple-nvr",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "smart-parking",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                            {"name": "npu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "motion-detection",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                            {"name": "npu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "license-plate-recognition",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "human-pose-detection",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                            {"name": "npu", "test_cases": default_test_cases},
                        ],
                    },
                    {
                        "pipeline_id": "segmentation",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                        ],
                    },
                ],
            },
            {
                "name": "Manufacturing Suite",
                "description": "Manufacturing benchmark suite covering defect detection.",
                "workloads": [
                    {
                        "pipeline_id": "defect-detection",
                        "variants": [
                            {"name": "cpu", "test_cases": default_test_cases},
                            {"name": "gpu", "test_cases": default_test_cases},
                            {"name": "npu", "test_cases": default_test_cases},
                        ],
                    },
                ],
            },
        ]

        for suite_spec in suite_specs:
            suite_slug = slugify_text(suite_spec["name"])
            suite = await session.scalar(
                select(BenchmarkSuite).where(BenchmarkSuite.slug == suite_slug)
            )

            if suite is None:
                now = datetime.now(timezone.utc)
                suite = BenchmarkSuite(
                    slug=suite_slug,
                    name=suite_spec["name"],
                    description=suite_spec["description"],
                    created_at=now,
                    last_run_at=now,
                )
                session.add(suite)
                await session.flush()
            else:
                suite.name = suite_spec["name"]
                suite.description = suite_spec["description"]

            for workload_spec in suite_spec["workloads"]:
                variant_names = [variant_spec["name"] for variant_spec in workload_spec["variants"]]
                variants_value = ",".join(variant_names)

                workload = await session.scalar(
                    select(BenchmarkWorkload).where(
                        BenchmarkWorkload.suite_id == suite.id,
                        BenchmarkWorkload.pipeline_id == workload_spec["pipeline_id"],
                        BenchmarkWorkload.variants == variants_value,
                    )
                )

                if workload is None:
                    workload = BenchmarkWorkload(
                        suite_id=suite.id,
                        pipeline_id=workload_spec["pipeline_id"],
                        variants=variants_value,
                    )
                    session.add(workload)
                    await session.flush()

                for variant_spec in workload_spec["variants"]:
                    variant_name = variant_spec["name"]
                    test_cases = variant_spec["test_cases"]

                    for streams in test_cases:
                        existing_test_case = await session.scalar(
                            select(BenchmarkTestCase).where(
                                BenchmarkTestCase.workload_id == workload.id,
                                BenchmarkTestCase.variant_id == variant_name,
                                BenchmarkTestCase.streams == streams,
                            )
                        )
                        if existing_test_case is None:
                            session.add(
                                BenchmarkTestCase(
                                    workload_id=workload.id,
                                    variant_id=variant_name,
                                    streams=streams,
                                )
                            )

        await session.commit()
        logger.info("Database seed ensured startup benchmark suite data")
