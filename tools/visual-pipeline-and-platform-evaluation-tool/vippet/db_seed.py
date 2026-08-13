"""Database seed data loaded during application startup."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import yaml

from orm_models import BenchmarkSuite, BenchmarkTestCase, BenchmarkWorkload
from utils import slugify_text

logger = logging.getLogger(__name__)


SeedLoader = Callable[[], list[Any]]
SeedApplier = Callable[[AsyncSession, list[Any]], Awaitable[None]]


class SeedObjectSpec(TypedDict):
    """Registration for one database seed object type."""

    name: str
    loader: SeedLoader
    applier: SeedApplier


class VariantSpec(TypedDict):
    """Single hardware variant benchmark configuration."""

    name: str
    test_cases: list[int]


class WorkloadSpec(TypedDict):
    """Single workload benchmark configuration."""

    pipeline_id: str
    variants: list[VariantSpec]


class SuiteSpec(TypedDict):
    """Top-level benchmark suite configuration."""

    name: str
    description: str
    workloads: list[WorkloadSpec]


class PipelineSeedSpec(TypedDict):
    """Placeholder pipeline seed configuration for future DB persistence."""

    name: str
    variants: list[dict[str, Any]]


def _load_benchmark_suite_specs() -> list[SuiteSpec]:
    """Load benchmark suite definitions from YAML files."""
    benchmarks_dir = Path(__file__).resolve().parent / "benchmarks"
    suite_specs: list[SuiteSpec] = []
    benchmark_files = sorted(benchmarks_dir.glob("*.yaml")) + sorted(
        benchmarks_dir.glob("*.yml")
    )

    if not benchmarks_dir.is_dir():
        logger.warning("Benchmarks directory is missing: %s", benchmarks_dir)
        return suite_specs

    if not benchmark_files:
        logger.warning(
            "No benchmark YAML files were found in %s. Expected one suite per file.",
            benchmarks_dir,
        )
        return suite_specs

    for suite_path in benchmark_files:
        with open(suite_path, "r", encoding="utf-8") as suite_file:
            loaded = yaml.safe_load(suite_file) or {}

        if not isinstance(loaded, dict):
            logger.warning(
                "Skipping benchmark seed file %s: expected mapping at top level",
                suite_path,
            )
            continue

        name = loaded.get("name")
        description = loaded.get("description")
        workloads = loaded.get("workloads")

        if not isinstance(name, str) or not isinstance(description, str):
            logger.warning(
                "Skipping benchmark seed file %s: 'name' and 'description' must be strings",
                suite_path,
            )
            continue
        if not isinstance(workloads, list):
            logger.warning(
                "Skipping benchmark seed file %s: 'workloads' must be a list",
                suite_path,
            )
            continue

        suite_specs.append(
            SuiteSpec(name=name, description=description, workloads=workloads)
        )

    return suite_specs


def _load_pipeline_seed_specs_placeholder() -> list[PipelineSeedSpec]:
    """Placeholder for future pipeline definitions loaded into DB from YAML."""
    logger.info(
        "Pipeline DB seed loader is not implemented yet. "
        "Future work: load pipeline definitions from YAML files."
    )
    return []


async def _seed_pipeline_definitions_placeholder(
    _session: AsyncSession,
    _pipeline_specs: list[PipelineSeedSpec],
) -> None:
    """Placeholder applier for future pipeline-definition DB seed entries."""
    return None


async def _seed_benchmark_suites(
    session: AsyncSession,
    suite_specs: list[SuiteSpec],
) -> None:
    """Seed benchmark suites, workloads, and test cases idempotently."""
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
            variant_names = [
                variant_spec["name"] for variant_spec in workload_spec["variants"]
            ]
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


def _get_seed_object_specs() -> list[SeedObjectSpec]:
    """Return all startup seed object registrations."""
    return [
        SeedObjectSpec(
            name="benchmark suites",
            loader=_load_benchmark_suite_specs,
            applier=_seed_benchmark_suites,
        ),
        SeedObjectSpec(
            name="pipeline definitions (placeholder)",
            loader=_load_pipeline_seed_specs_placeholder,
            applier=_seed_pipeline_definitions_placeholder,
        ),
    ]


async def seed_initial_data(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """
    Insert initial rows in an idempotent way.

    Seeding runs on startup after schema creation.
    """
    async with session_maker() as session:
        for seed_object_spec in _get_seed_object_specs():
            loaded_objects = seed_object_spec["loader"]()
            await seed_object_spec["applier"](session, loaded_objects)
            logger.info(
                "Database seed loaded %d entries for %s",
                len(loaded_objects),
                seed_object_spec["name"],
            )

        await session.commit()
