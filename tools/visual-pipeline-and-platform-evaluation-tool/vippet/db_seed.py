"""Database seed data loaded during application startup."""

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import yaml

from models import GENAI_SENTINEL_FILE, MODELS_PATH
from orm_models import (
    BenchmarkSuite,
    BenchmarkTestCase,
    BenchmarkWorkload,
    Model,
    ModelVariant,
)
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
    number_of_streams: list[int]


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


class ModelPrecisionSpec(TypedDict):
    """Single (precision, model-proc) entry for a catalog model."""

    precision: str
    model_path: str
    model_proc: str | None


class ModelCatalogSpec(TypedDict):
    """Top-level model catalog entry loaded from vippet/models/*.yaml."""

    name: str
    display_name: str
    description: str | None
    source: str
    hub: str
    category: str
    unsupported_devices: str | None
    precisions: list[ModelPrecisionSpec]
    extra_model_procs: list[str]
    download_request: dict[str, Any] | None


def _validate_benchmark_suite_spec(
    loaded: Any,
    suite_path: Path,
) -> SuiteSpec | None:
    """Validate a benchmark YAML mapping and return a cleaned suite spec."""
    if not isinstance(loaded, dict):
        logger.warning(
            "Skipping benchmark seed file %s: expected mapping at top level",
            suite_path,
        )
        return None

    name = loaded.get("name")
    description = loaded.get("description")
    workloads = loaded.get("workloads")

    if not isinstance(name, str) or not name.strip():
        logger.warning(
            "Skipping benchmark seed file %s: 'name' must be a non-empty string",
            suite_path,
        )
        return None
    if not isinstance(description, str) or not description.strip():
        logger.warning(
            "Skipping benchmark seed file %s: 'description' must be a non-empty string",
            suite_path,
        )
        return None
    if not isinstance(workloads, list):
        logger.warning(
            "Skipping benchmark seed file %s: 'workloads' must be a list",
            suite_path,
        )
        return None

    valid_workloads: list[WorkloadSpec] = []
    for workload_index, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            logger.warning(
                "Skipping invalid workload #%d in %s: expected mapping",
                workload_index,
                suite_path,
            )
            continue

        pipeline_id = workload.get("pipeline_id")
        variants = workload.get("variants")

        if not isinstance(pipeline_id, str) or not pipeline_id.strip():
            logger.warning(
                "Skipping invalid workload #%d in %s: 'pipeline_id' must be a non-empty string",
                workload_index,
                suite_path,
            )
            continue
        if not isinstance(variants, list):
            logger.warning(
                "Skipping workload '%s' in %s: 'variants' must be a list",
                pipeline_id,
                suite_path,
            )
            continue

        valid_variants: list[VariantSpec] = []
        for variant_index, variant in enumerate(variants):
            if not isinstance(variant, dict):
                logger.warning(
                    "Skipping invalid variant #%d in workload '%s' from %s: expected mapping",
                    variant_index,
                    pipeline_id,
                    suite_path,
                )
                continue

            variant_name = variant.get("name")
            stream_values = variant.get("number_of_streams", variant.get("test_cases"))

            if not isinstance(variant_name, str) or not variant_name.strip():
                logger.warning(
                    "Skipping invalid variant #%d in workload '%s' from %s: 'name' must be a non-empty string",
                    variant_index,
                    pipeline_id,
                    suite_path,
                )
                continue
            if not isinstance(stream_values, list):
                logger.warning(
                    "Skipping variant '%s' in workload '%s' from %s: 'number_of_streams' must be a list",
                    variant_name,
                    pipeline_id,
                    suite_path,
                )
                continue

            normalized_streams: list[int] = []
            for stream_index, stream_value in enumerate(stream_values):
                if not isinstance(stream_value, int) or isinstance(stream_value, bool):
                    logger.warning(
                        "Skipping stream value #%d for variant '%s' in workload '%s' from %s: expected integer",
                        stream_index,
                        variant_name,
                        pipeline_id,
                        suite_path,
                    )
                    continue
                if stream_value < 1:
                    logger.warning(
                        "Skipping stream value #%d for variant '%s' in workload '%s' from %s: stream count must be positive",
                        stream_index,
                        variant_name,
                        pipeline_id,
                        suite_path,
                    )
                    continue
                normalized_streams.append(stream_value)

            if not normalized_streams:
                logger.warning(
                    "Skipping variant '%s' in workload '%s' from %s: no valid stream counts found",
                    variant_name,
                    pipeline_id,
                    suite_path,
                )
                continue

            valid_variants.append(
                VariantSpec(name=variant_name, number_of_streams=normalized_streams)
            )

        if not valid_variants:
            logger.warning(
                "Skipping workload '%s' in %s: no valid variants remain after validation",
                pipeline_id,
                suite_path,
            )
            continue

        valid_workloads.append(
            WorkloadSpec(pipeline_id=pipeline_id, variants=valid_variants)
        )

    if not valid_workloads:
        logger.warning(
            "Skipping benchmark seed file %s: no valid workloads found after validation",
            suite_path,
        )
        return None

    return SuiteSpec(
        name=name.strip(),
        description=description.strip(),
        workloads=valid_workloads,
    )


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
        try:
            with open(suite_path, "r", encoding="utf-8") as suite_file:
                loaded = yaml.safe_load(suite_file) or {}
        except (OSError, yaml.YAMLError, ValueError, TypeError) as exc:
            logger.exception(
                "Skipping benchmark seed file %s due to YAML read/parse error: %s",
                suite_path,
                exc,
            )
            continue

        validated_suite = _validate_benchmark_suite_spec(loaded, suite_path)
        if validated_suite is None:
            continue

        suite_specs.append(validated_suite)

    return suite_specs


def _validate_model_catalog_spec(
    loaded: Any,
    model_path: Path,
) -> ModelCatalogSpec | None:
    """Validate one vippet/models/*.yaml mapping."""
    if not isinstance(loaded, dict):
        logger.warning(
            "Skipping model catalog file %s: expected mapping at top level",
            model_path,
        )
        return None

    name = loaded.get("name")
    display_name = loaded.get("display_name")
    source = loaded.get("source")
    category = loaded.get("type")
    precisions = loaded.get("precisions")

    if not isinstance(name, str) or not name.strip():
        logger.warning(
            "Skipping model catalog file %s: 'name' must be a non-empty string",
            model_path,
        )
        return None
    if not isinstance(display_name, str) or not display_name.strip():
        logger.warning(
            "Skipping model catalog file %s: 'display_name' must be a non-empty string",
            model_path,
        )
        return None
    if not isinstance(source, str) or not source.strip():
        logger.warning(
            "Skipping model catalog file %s: 'source' must be a non-empty string",
            model_path,
        )
        return None
    if not isinstance(category, str) or not category.strip():
        logger.warning(
            "Skipping model catalog file %s: 'type' must be a non-empty string",
            model_path,
        )
        return None
    if not isinstance(precisions, list) or not precisions:
        logger.warning(
            "Skipping model catalog file %s: 'precisions' must be a non-empty list",
            model_path,
        )
        return None

    valid_precisions: list[ModelPrecisionSpec] = []
    for precision_index, prec_entry in enumerate(precisions):
        if not isinstance(prec_entry, dict):
            logger.warning(
                "Skipping invalid precision #%d in %s: expected mapping",
                precision_index,
                model_path,
            )
            continue
        precision = prec_entry.get("precision")
        prec_model_path = prec_entry.get("model_path")
        if not isinstance(precision, str) or not precision.strip():
            logger.warning(
                "Skipping precision #%d in %s: 'precision' must be a non-empty string",
                precision_index,
                model_path,
            )
            continue
        if not isinstance(prec_model_path, str) or not prec_model_path.strip():
            logger.warning(
                "Skipping precision #%d in %s: 'model_path' must be a non-empty string",
                precision_index,
                model_path,
            )
            continue
        model_proc_raw = prec_entry.get("model_proc")
        model_proc = (
            model_proc_raw.strip()
            if isinstance(model_proc_raw, str) and model_proc_raw.strip()
            else None
        )
        valid_precisions.append(
            ModelPrecisionSpec(
                precision=precision.strip(),
                model_path=prec_model_path.strip(),
                model_proc=model_proc,
            )
        )

    if not valid_precisions:
        logger.warning(
            "Skipping model catalog file %s: no valid precisions found after validation",
            model_path,
        )
        return None

    description_raw = loaded.get("description")
    description = (
        description_raw.strip()
        if isinstance(description_raw, str) and description_raw.strip()
        else None
    )
    hub_raw = loaded.get("hub")
    hub = hub_raw.strip() if isinstance(hub_raw, str) and hub_raw.strip() else source
    unsupported_devices_raw = loaded.get("unsupported_devices")
    unsupported_devices = (
        unsupported_devices_raw.strip()
        if isinstance(unsupported_devices_raw, str) and unsupported_devices_raw.strip()
        else None
    )
    extra_model_procs_raw = loaded.get("extra_model_procs")
    extra_model_procs = (
        [p.strip() for p in extra_model_procs_raw if isinstance(p, str) and p.strip()]
        if isinstance(extra_model_procs_raw, list)
        else []
    )
    download_request_raw = loaded.get("download_request")
    download_request = (
        download_request_raw if isinstance(download_request_raw, dict) else None
    )

    return ModelCatalogSpec(
        name=name.strip(),
        display_name=display_name.strip(),
        description=description,
        source=source.strip(),
        hub=hub,
        category=category.strip(),
        unsupported_devices=unsupported_devices,
        precisions=valid_precisions,
        extra_model_procs=extra_model_procs,
        download_request=download_request,
    )


def _load_model_catalog_specs() -> list[ModelCatalogSpec]:
    """Load one-model-per-file catalog definitions from vippet/models/."""
    catalog_dir = Path(__file__).resolve().parent / "models"
    model_specs: list[ModelCatalogSpec] = []

    if not catalog_dir.is_dir():
        logger.warning("Models catalog directory is missing: %s", catalog_dir)
        return model_specs

    catalog_files = sorted(catalog_dir.glob("*.yaml")) + sorted(
        catalog_dir.glob("*.yml")
    )
    if not catalog_files:
        logger.warning(
            "No model catalog YAML files were found in %s. Expected one model per file.",
            catalog_dir,
        )
        return model_specs

    for model_file in catalog_files:
        try:
            with open(model_file, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError, ValueError, TypeError) as exc:
            logger.exception(
                "Skipping model catalog file %s due to YAML read/parse error: %s",
                model_file,
                exc,
            )
            continue

        validated_model = _validate_model_catalog_spec(loaded, model_file)
        if validated_model is None:
            continue

        model_specs.append(validated_model)

    return model_specs


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
                number_of_streams = variant_spec.get(
                    "number_of_streams", variant_spec.get("test_cases", [])
                )

                for streams in number_of_streams:
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


def _variant_installed_on_disk(category: str, model_path_full: str) -> bool:
    """One-time disk check used only when a variant row is first created.

    Mirrors ``SupportedModel.exists_on_disk()``: vision-language models
    are directories that must contain ``GENAI_SENTINEL_FILE``; every
    other category is a single model file.
    """
    if category == "vision_language_models":
        return os.path.isfile(os.path.join(model_path_full, GENAI_SENTINEL_FILE))
    return os.path.isfile(model_path_full)


def _build_variant_rows(spec: ModelCatalogSpec) -> list[dict[str, Any]]:
    """Fan a canonical catalog spec out into one row per selectable variant.

    Mirrors ``SupportedModelsManager.__init__``'s expansion: one entry per
    precision, plus one additional entry per ``extra_model_procs`` alias
    per precision. ``name``/``display_name`` only gain a
    ``_<procfilename>`` / ``[model-proc: ...]`` suffix when the precision
    has its own ``model_proc`` AND ``extra_model_procs`` is non-empty -
    otherwise every precision of the model shares the same ``name``.
    """
    name = spec["name"]
    display_name = spec["display_name"]
    extra_model_procs = spec["extra_model_procs"]
    has_extra_procs = bool(extra_model_procs)
    rows: list[dict[str, Any]] = []

    for prec_entry in spec["precisions"]:
        precision = prec_entry["precision"]
        model_path = prec_entry["model_path"]
        model_proc = prec_entry["model_proc"]
        prec_display_name = f"{display_name} ({precision})"

        if has_extra_procs and model_proc:
            proc_filename = Path(model_proc).stem
            variant_name = f"{name}_{proc_filename}"
            variant_display_name = f"{prec_display_name} [model-proc: {proc_filename}]"
        else:
            variant_name = name
            variant_display_name = prec_display_name

        rows.append(
            {
                "name": variant_name,
                "display_name": variant_display_name,
                "precision": precision,
                "model_path": model_path,
                "model_proc": model_proc,
            }
        )

        for extra_proc in extra_model_procs:
            proc_filename = Path(extra_proc).stem
            rows.append(
                {
                    "name": f"{name}_{proc_filename}",
                    "display_name": f"{prec_display_name} [model-proc: {proc_filename}]",
                    "precision": precision,
                    "model_path": model_path,
                    "model_proc": extra_proc,
                }
            )

    return rows


async def _seed_models(
    session: AsyncSession,
    model_specs: list[ModelCatalogSpec],
) -> None:
    """Insert-only seeding of the model catalog.

    A model already present in the DB (matched by canonical ``name``) is
    never touched - editing/removing its YAML file has no effect on an
    existing row. Disk existence is checked exactly once, at the moment
    a model/variant row is first created, to backfill install_status for
    models installed under the pre-DB system; it is never re-checked on
    later startups.
    """
    for spec in model_specs:
        existing = await session.scalar(select(Model).where(Model.name == spec["name"]))
        if existing is not None:
            continue

        now = datetime.now(timezone.utc)
        variant_rows = _build_variant_rows(spec)
        installed_flags = [
            _variant_installed_on_disk(
                spec["category"],
                os.path.join(MODELS_PATH, os.path.normpath(row["model_path"])),
            )
            for row in variant_rows
        ]
        model_installed = any(installed_flags)

        model = Model(
            name=spec["name"],
            display_name=spec["display_name"],
            description=spec["description"],
            category=spec["category"],
            source=spec["source"],
            hub=spec["hub"],
            unsupported_devices=spec["unsupported_devices"],
            is_custom=False,
            install_status="installed" if model_installed else "not_installed",
            installed_at=now if model_installed else None,
            download_request=spec["download_request"],
            created_at=now,
        )
        session.add(model)
        await session.flush()

        for row, installed in zip(variant_rows, installed_flags):
            session.add(
                ModelVariant(
                    model_id=model.id,
                    name=row["name"],
                    display_name=row["display_name"],
                    precision=row["precision"],
                    model_path=row["model_path"],
                    model_proc=row["model_proc"],
                    installed=installed,
                    installed_at=now if installed else None,
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
            name="models",
            loader=_load_model_catalog_specs,
            applier=_seed_models,
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
