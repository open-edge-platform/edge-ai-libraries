"""Fan-out aggregation across all registered ViPPET instances."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import schemas
from .config import settings
from .db import (
    Experiment,
    ExperimentRun,
    Instance,
    SessionLocal,
    TestExperiment,
    TestExperimentRun,
)
from .vippet_client import VippetClient, VippetUnavailable, make_http_client

logger = logging.getLogger("portal.aggregator")

BENCHMARK_METRICS = [
    "total_fps",
    "per_stream_fps",
    "latency_avg_ms",
    "cpu_usage",
    "gpu_usage",
    "npu_usage",
    "memory_usage",
    "power_usage",
    "score_total",
    "score_performance",
    "score_efficiency",
]

PERFORMANCE_METRICS = ["total_fps", "per_stream_fps", "total_streams", "elapsed_time"]
DENSITY_METRICS = ["total_streams", "per_stream_fps", "fps_floor", "elapsed_time"]


class _TtlCache:
    def __init__(self, ttl: int) -> None:
        self._ttl = ttl
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if time.monotonic() - stored_at > self._ttl:
            self._entries.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._entries[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._entries.clear()


_cache = _TtlCache(settings.cache_ttl)
_http_client = None


def http_client():
    global _http_client
    if _http_client is None:
        _http_client = make_http_client()
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def invalidate_cache() -> None:
    _cache.clear()


async def list_instances(session: AsyncSession, *, only_enabled: bool = False) -> list[Instance]:
    statement = select(Instance).order_by(Instance.id)
    if only_enabled:
        statement = statement.where(Instance.enabled.is_(True))
    return list((await session.scalars(statement)).all())


def _client(instance: Instance) -> VippetClient:
    return VippetClient(instance.url, http_client())


def _instance_ref(instance: Instance) -> dict[str, Any]:
    return {
        "instance_id": instance.id,
        "instance_name": instance.name,
        "instance_url": instance.url,
        "cpu": instance.cpu,
    }


async def _gather_per_instance(
    instances: Sequence[Instance],
    task: Callable[[Instance], Any],
) -> list[tuple[Instance, Any | None, str | None]]:
    """Run `task` for every instance, isolating failures per instance."""
    results = await asyncio.gather(
        *(task(instance) for instance in instances), return_exceptions=True
    )
    out: list[tuple[Instance, Any | None, str | None]] = []
    for instance, result in zip(instances, results):
        if isinstance(result, BaseException):
            out.append((instance, None, str(result) or result.__class__.__name__))
        else:
            out.append((instance, result, None))
    return out


# --------------------------------------------------------------------------- #
# Instance health
# --------------------------------------------------------------------------- #


async def _probe(instance: Instance) -> dict[str, Any]:
    client = _client(instance)
    status, devices, runs, perf, density = await asyncio.gather(
        client.status(),
        client.devices(),
        client.benchmark_runs(),
        client.job_statuses("performance"),
        client.job_statuses("density"),
        return_exceptions=True,
    )
    if isinstance(status, BaseException):
        raise VippetUnavailable("instance unreachable")

    def safe_list(value: Any) -> list[dict[str, Any]]:
        return value if isinstance(value, list) else []

    device_list = safe_list(devices)
    by_family = {d.get("device_family"): d.get("full_device_name") for d in device_list}
    run_list = safe_list(runs)
    scores = [r["score_total"] for r in run_list if r.get("score_total") is not None]
    start_times = [r["start_time"] for r in run_list if r.get("start_time")]

    return {
        "status": status.get("status"),
        "ready": bool(status.get("ready")),
        "version": status.get("version"),
        "cpu": by_family.get("CPU"),
        "gpu": by_family.get("GPU"),
        "npu": by_family.get("NPU"),
        "benchmark_run_count": len(run_list),
        "performance_job_count": len(safe_list(perf)),
        "density_job_count": len(safe_list(density)),
        "best_score": max(scores) if scores else None,
        "last_run_time": max(start_times) if start_times else None,
    }


async def instance_health(session: AsyncSession) -> list[schemas.InstanceHealth]:
    instances = await list_instances(session)
    probed = await _gather_per_instance(instances, _probe)

    health: list[schemas.InstanceHealth] = []
    dirty = False
    for instance, info, error in probed:
        base = {
            "id": instance.id,
            "name": instance.name,
            "url": instance.url,
            "enabled": instance.enabled,
            "notes": instance.notes,
            "cpu": instance.cpu,
            "gpu": instance.gpu,
            "npu": instance.npu,
            "version": instance.version,
        }
        if info is None:
            health.append(schemas.InstanceHealth(**base, reachable=False, error=error))
            continue

        for attribute in ("cpu", "gpu", "npu", "version"):
            value = info.get(attribute)
            if value and getattr(instance, attribute) != value:
                setattr(instance, attribute, value)
                dirty = True
        base.update(
            cpu=instance.cpu, gpu=instance.gpu, npu=instance.npu, version=instance.version
        )
        health.append(
            schemas.InstanceHealth(
                **base,
                reachable=True,
                ready=info["ready"],
                status=info["status"],
                benchmark_run_count=info["benchmark_run_count"],
                performance_job_count=info["performance_job_count"],
                density_job_count=info["density_job_count"],
                best_score=info["best_score"],
                last_run_time=info["last_run_time"],
            )
        )

    if dirty:
        await session.commit()
    return health


# --------------------------------------------------------------------------- #
# Benchmark runs
# --------------------------------------------------------------------------- #


async def benchmark_runs(session: AsyncSession) -> list[schemas.BenchmarkRun]:
    instances = await list_instances(session, only_enabled=True)
    gathered = await _gather_per_instance(instances, lambda i: _client(i).benchmark_runs())

    runs: list[schemas.BenchmarkRun] = []
    for instance, payload, error in gathered:
        if error or not payload:
            continue
        for run in payload:
            runs.append(
                schemas.BenchmarkRun(
                    **_instance_ref(instance),
                    id=run["id"],
                    suite_slug=run["suite_slug"],
                    suite_name=run.get("suite_name"),
                    status=run.get("status", "unknown"),
                    score_total=run.get("score_total"),
                    score_performance=run.get("score_performance"),
                    score_efficiency=run.get("score_efficiency"),
                    start_time=run.get("start_time") or 0,
                    execution_time=run.get("execution_time"),
                    total_test_cases=run.get("total_test_cases"),
                    passed_test_cases=run.get("passed_test_cases"),
                    ref=f"{instance.id}:{run['suite_slug']}:{run['id']}",
                )
            )
    runs.sort(key=lambda run: run.start_time, reverse=True)
    return runs


def parse_benchmark_ref(ref: str) -> tuple[int, str, int]:
    instance_id, suite_slug, run_id = ref.split(":", 2)
    return int(instance_id), suite_slug, int(run_id)


def parse_job_ref(ref: str) -> tuple[int, str]:
    instance_id, job_id = ref.split(":", 1)
    return int(instance_id), job_id


def _strip_samples(details: dict[str, Any]) -> dict[str, Any]:
    """Drop the embedded raw telemetry series (megabytes per run)."""
    for workload in details.get("workload_runs") or []:
        for test_case in workload.get("test_case_runs") or []:
            test_case.pop("metrics", None)
    return details


async def benchmark_run_details(
    session: AsyncSession, ref: str
) -> tuple[Instance, dict[str, Any]]:
    instance_id, suite_slug, run_id = parse_benchmark_ref(ref)
    instance = await session.get(Instance, instance_id)
    if instance is None:
        raise KeyError(f"unknown instance {instance_id}")

    cache_key = f"bench:{ref}"
    cached = _cache.get(cache_key)
    if cached is None:
        cached = _strip_samples(await _client(instance).benchmark_run_details(suite_slug, run_id))
        if cached.get("status") in {"completed", "failed", "cancelled"}:
            _cache.set(cache_key, cached)
    return instance, cached


def _pass_rate(details: dict[str, Any]) -> float | None:
    total = details.get("total_test_cases") or 0
    if not total:
        return None
    return round((details.get("passed_test_cases") or 0) / total * 100, 1)


async def compare_benchmarks(session: AsyncSession, refs: Sequence[str]) -> schemas.Comparison:
    columns: list[schemas.ComparisonColumn] = []
    rows: dict[str, schemas.ComparisonRow] = {}
    errors: dict[str, str] = {}

    fetched = await asyncio.gather(
        *(benchmark_run_details(session, ref) for ref in refs), return_exceptions=True
    )

    for ref, result in zip(refs, fetched):
        if isinstance(result, BaseException):
            errors[ref] = str(result) or result.__class__.__name__
            continue
        instance, details = result
        columns.append(
            schemas.ComparisonColumn(
                ref=ref,
                label=f"{instance.name} · {details.get('suite_name') or details.get('suite_slug')} #{details.get('id')}",
                instance_id=instance.id,
                instance_name=instance.name,
                cpu=instance.cpu,
                status=details.get("status"),
                start_time=details.get("start_time"),
                summary={
                    "score_total": details.get("score_total"),
                    "score_performance": details.get("score_performance"),
                    "score_efficiency": details.get("score_efficiency"),
                    "pass_rate": _pass_rate(details),
                    "execution_time": details.get("execution_time"),
                },
            )
        )

        for workload in details.get("workload_runs") or []:
            pipeline_id = workload.get("pipeline_id") or f"workload-{workload.get('workload_id')}"
            workload_key = f"{pipeline_id}::_suite_"
            row = rows.setdefault(
                workload_key,
                schemas.ComparisonRow(key=workload_key, label=pipeline_id, group=pipeline_id),
            )
            row.cells[ref] = {
                "status": workload.get("status"),
                "score_total": workload.get("score_total"),
                "score_performance": workload.get("score_performance"),
                "score_efficiency": workload.get("score_efficiency"),
            }

            for test_case in workload.get("test_case_runs") or []:
                variant = test_case.get("variant_id") or "default"
                streams = test_case.get("streams")
                key = f"{pipeline_id}::{variant}::{streams}"
                case_row = rows.setdefault(
                    key,
                    schemas.ComparisonRow(
                        key=key,
                        label=f"{variant} · {streams} stream{'s' if streams != 1 else ''}",
                        group=pipeline_id,
                    ),
                )
                case_row.cells[ref] = {
                    metric: test_case.get(metric) for metric in BENCHMARK_METRICS
                } | {"status": test_case.get("status")}

    return schemas.Comparison(
        columns=columns,
        rows=sorted(rows.values(), key=_benchmark_row_sort_key),
        metrics=BENCHMARK_METRICS,
        errors=errors,
    )


def _benchmark_row_sort_key(row: schemas.ComparisonRow) -> tuple[str, int, str, int]:
    """Group by workload, suite row first, then variant and stream count numerically."""
    _, _, remainder = row.key.partition("::")
    if remainder == "_suite_":
        return (row.group or "", 0, "", 0)
    variant, _, streams = remainder.partition("::")
    return (row.group or "", 1, variant, int(streams) if streams.isdigit() else 0)


# --------------------------------------------------------------------------- #
# Portal-driven experiments
# --------------------------------------------------------------------------- #


async def benchmark_suites(session: AsyncSession) -> list[schemas.BenchmarkSuite]:
    """Suites offered by the enabled machines, merged by slug."""
    instances = await list_instances(session, only_enabled=True)
    gathered = await _gather_per_instance(instances, lambda i: _client(i).benchmark_suites())

    suites: dict[str, schemas.BenchmarkSuite] = {}
    for instance, payload, error in gathered:
        if error or not payload:
            continue
        for suite in payload:
            slug = suite.get("slug")
            if not slug:
                continue
            merged = suites.get(slug)
            if merged is None:
                merged = schemas.BenchmarkSuite(
                    slug=slug,
                    name=suite.get("name") or slug,
                    description=suite.get("description"),
                    workload_count=len(suite.get("workloads") or []),
                )
                suites[slug] = merged
            merged.instance_ids.append(instance.id)
    return sorted(suites.values(), key=lambda suite: suite.name.lower())


async def start_experiment(
    session: AsyncSession, payload: schemas.ExperimentCreate
) -> schemas.Experiment:
    """Launch one suite on several machines at once and remember the grouping."""
    wanted = set(payload.instance_ids)
    instances = [i for i in await list_instances(session, only_enabled=True) if i.id in wanted]
    if not instances:
        raise ValueError("none of the selected machines is enabled")

    suite_name = next(
        (s.name for s in await benchmark_suites(session) if s.slug == payload.suite_slug), None
    )
    started = await _gather_per_instance(
        instances, lambda i: _client(i).start_benchmark_suite(payload.suite_slug)
    )

    experiment = Experiment(suite_slug=payload.suite_slug, suite_name=suite_name)
    session.add(experiment)
    await session.flush()
    for instance, job_id, error in started:
        session.add(
            ExperimentRun(
                experiment_id=experiment.id,
                instance_id=instance.id,
                job_id=job_id,
                error=error,
            )
        )
    await session.commit()

    invalidate_cache()
    return (await _build_experiments(session, [experiment]))[0]


async def experiments(session: AsyncSession) -> list[schemas.Experiment]:
    records = list(
        (await session.scalars(select(Experiment).order_by(Experiment.id.desc()))).all()
    )
    return await _build_experiments(session, records)


async def delete_experiment(session: AsyncSession, experiment_id: int) -> None:
    record = await session.get(Experiment, experiment_id)
    if record is None:
        raise KeyError(f"unknown experiment {experiment_id}")
    await session.execute(
        delete(ExperimentRun).where(ExperimentRun.experiment_id == experiment_id)
    )
    await session.delete(record)
    await session.commit()


async def _benchmark_job_snapshot(
    instance: Instance,
) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Benchmark jobs keyed by job id, and suite runs keyed by suite run id."""
    client = _client(instance)
    jobs, runs = await asyncio.gather(
        client.benchmark_job_statuses(), client.benchmark_runs(), return_exceptions=True
    )
    job_map: dict[str, dict[str, Any]] = {}
    if isinstance(jobs, list):
        job_map = {str(j["id"]): j for j in jobs if isinstance(j, dict) and j.get("id")}
    run_map: dict[int, dict[str, Any]] = {}
    if isinstance(runs, list):
        run_map = {r["id"]: r for r in runs if isinstance(r, dict) and r.get("id") is not None}
    return job_map, run_map


async def _build_experiments(
    session: AsyncSession, records: Sequence[Experiment]
) -> list[schemas.Experiment]:
    if not records:
        return []

    rows = list(
        (
            await session.scalars(
                select(ExperimentRun).where(
                    ExperimentRun.experiment_id.in_([r.id for r in records])
                )
            )
        ).all()
    )
    instances = {instance.id: instance for instance in await list_instances(session)}

    snapshots: dict[int, tuple[dict[str, Any], dict[int, Any]]] = {}
    targets = [instances[i] for i in sorted({r.instance_id for r in rows}) if i in instances]
    for instance, snapshot, _error in await _gather_per_instance(targets, _benchmark_job_snapshot):
        snapshots[instance.id] = snapshot or ({}, {})

    grouped: dict[int, list[ExperimentRun]] = {}
    for row in rows:
        grouped.setdefault(row.experiment_id, []).append(row)

    built: list[schemas.Experiment] = []
    for record in records:
        runs = [
            _experiment_run(row, instances[row.instance_id], snapshots.get(row.instance_id))
            for row in grouped.get(record.id, [])
            if row.instance_id in instances
        ]
        runs.sort(key=lambda run: run.instance_name.lower())
        built.append(
            schemas.Experiment(
                id=record.id,
                suite_slug=record.suite_slug,
                suite_name=record.suite_name,
                created_at=record.created_at,
                state=_rollup_state(run.state for run in runs),
                runs=runs,
            )
        )
    return built


def _experiment_run(
    row: ExperimentRun,
    instance: Instance,
    snapshot: tuple[dict[str, Any], dict[int, Any]] | None,
) -> schemas.ExperimentRun:
    jobs, suite_runs = snapshot or ({}, {})
    job = jobs.get(row.job_id) if row.job_id else None
    suite_run = suite_runs.get(job.get("suite_run_id")) if job else None

    if row.error:
        state = "FAILED"
    elif job is None:
        state = "UNKNOWN"
    else:
        state = str(job.get("state") or "UNKNOWN")

    return schemas.ExperimentRun(
        instance_id=instance.id,
        instance_name=instance.name,
        cpu=instance.cpu,
        job_id=row.job_id,
        state=state,
        error=row.error,
        start_time=(job or {}).get("start_time"),
        elapsed_time=(job or {}).get("elapsed_time"),
        total_test_cases=(job or {}).get("total_test_cases"),
        completed_test_cases=(job or {}).get("completed_test_cases"),
        score_total=(suite_run or {}).get("score_total"),
        score_performance=(suite_run or {}).get("score_performance"),
        score_efficiency=(suite_run or {}).get("score_efficiency"),
        ref=(
            f"{instance.id}:{suite_run['suite_slug']}:{suite_run['id']}" if suite_run else None
        ),
    )


def _experiment_state(runs: Sequence[schemas.ExperimentRun]) -> str:
    states = {run.state for run in runs}
    for candidate in ("RUNNING", "FAILED", "COMPLETED"):
        if candidate in states:
            return candidate
    return "UNKNOWN"


# --------------------------------------------------------------------------- #
# Portal-driven performance / density experiments
# --------------------------------------------------------------------------- #


async def pipeline_catalog(session: AsyncSession) -> list[schemas.Pipeline]:
    """Pipelines offered by the enabled machines, merged by id."""
    instances = await list_instances(session, only_enabled=True)
    gathered = await _gather_per_instance(instances, lambda i: _client(i).pipelines())

    catalog: dict[str, schemas.Pipeline] = {}
    for instance, payload, error in gathered:
        if error or not payload:
            continue
        for pipeline in payload:
            pipeline_id = pipeline.get("id")
            if not pipeline_id:
                continue
            merged = catalog.get(pipeline_id)
            if merged is None:
                merged = schemas.Pipeline(
                    id=pipeline_id, name=pipeline.get("name") or pipeline_id
                )
                catalog[pipeline_id] = merged
            known = {variant.id for variant in merged.variants}
            for variant in pipeline.get("variants") or []:
                variant_id = variant.get("id")
                if variant_id and variant_id not in known:
                    merged.variants.append(
                        schemas.PipelineVariant(
                            id=variant_id, name=variant.get("name") or variant_id
                        )
                    )
                    known.add(variant_id)
            merged.instance_ids.append(instance.id)
    return sorted(catalog.values(), key=lambda pipeline: pipeline.name.lower())


def _test_spec(kind: str, payload: schemas.TestExperimentCreate) -> dict[str, Any]:
    pipeline = {
        "source": "variant",
        "pipeline_id": payload.pipeline_id,
        "variant_id": payload.variant_id,
    }
    if kind == "density":
        return {
            "fps_floor": payload.fps_floor,
            "pipeline_density_specs": [{"pipeline": pipeline, "stream_rate": 100}],
            "execution_config": {
                "output_mode": "disabled",
                "max_runtime": payload.max_runtime,
                "metadata_mode": "disabled",
            },
        }
    return {
        "pipeline_performance_specs": [{"pipeline": pipeline, "streams": payload.streams}],
        "execution_config": {
            "output_mode": "disabled",
            "max_runtime": payload.max_runtime,
            "metadata_mode": "disabled",
        },
    }


async def start_test_experiment(
    session: AsyncSession, kind: str, payload: schemas.TestExperimentCreate
) -> schemas.TestExperiment:
    """Run one workload on several machines at once and group the resulting jobs."""
    wanted = set(payload.instance_ids)
    instances = [i for i in await list_instances(session, only_enabled=True) if i.id in wanted]
    if not instances:
        raise ValueError("none of the selected machines is enabled")

    catalog = {pipeline.id: pipeline for pipeline in await pipeline_catalog(session)}
    pipeline = catalog.get(payload.pipeline_id)
    if pipeline is None:
        raise ValueError(f"unknown pipeline {payload.pipeline_id}")
    variant = next((v for v in pipeline.variants if v.id == payload.variant_id), None)
    if variant is None:
        raise ValueError(f"unknown variant {payload.variant_id}")

    spec = _test_spec(kind, payload)
    started = await _gather_per_instance(instances, lambda i: _client(i).start_test(kind, spec))

    experiment = TestExperiment(
        kind=kind,
        pipeline_id=payload.pipeline_id,
        variant_id=payload.variant_id,
        label=f"{pipeline.name} · {variant.name}",
        streams=payload.streams if kind == "performance" else None,
        max_runtime=payload.max_runtime,
        fps_floor=payload.fps_floor if kind == "density" else None,
    )
    session.add(experiment)
    await session.flush()
    for instance, job_id, error in started:
        session.add(
            TestExperimentRun(
                experiment_id=experiment.id,
                instance_id=instance.id,
                job_id=job_id,
                error=error,
            )
        )
    await session.commit()

    invalidate_cache()
    return (await _build_test_experiments(session, [experiment]))[0]


async def test_experiments(session: AsyncSession, kind: str) -> list[schemas.TestExperiment]:
    records = list(
        (
            await session.scalars(
                select(TestExperiment)
                .where(TestExperiment.kind == kind)
                .order_by(TestExperiment.id.desc())
            )
        ).all()
    )
    return await _build_test_experiments(session, records)


async def delete_test_experiment(session: AsyncSession, experiment_id: int) -> None:
    record = await session.get(TestExperiment, experiment_id)
    if record is None:
        raise KeyError(f"unknown experiment {experiment_id}")
    await session.execute(
        delete(TestExperimentRun).where(TestExperimentRun.experiment_id == experiment_id)
    )
    await session.delete(record)
    await session.commit()


async def _build_test_experiments(
    session: AsyncSession, records: Sequence[TestExperiment]
) -> list[schemas.TestExperiment]:
    if not records:
        return []

    rows = list(
        (
            await session.scalars(
                select(TestExperimentRun).where(
                    TestExperimentRun.experiment_id.in_([r.id for r in records])
                )
            )
        ).all()
    )
    instances = {instance.id: instance for instance in await list_instances(session)}

    # One status fetch per (machine, kind) pair covers every experiment of that kind.
    kinds = {record.kind for record in records}
    jobs: dict[tuple[int, str], dict[str, dict[str, Any]]] = {}
    targets = [instances[i] for i in sorted({r.instance_id for r in rows}) if i in instances]
    for kind in kinds:
        gathered = await _gather_per_instance(targets, lambda i: _client(i).job_statuses(kind))
        for instance, payload, _error in gathered:
            jobs[(instance.id, kind)] = {
                str(job["id"]): job
                for job in (payload or [])
                if isinstance(job, dict) and job.get("id")
            }

    grouped: dict[int, list[TestExperimentRun]] = {}
    for row in rows:
        grouped.setdefault(row.experiment_id, []).append(row)

    built: list[schemas.TestExperiment] = []
    for record in records:
        runs = [
            _test_experiment_run(
                row, instances[row.instance_id], jobs.get((row.instance_id, record.kind), {})
            )
            for row in grouped.get(record.id, [])
            if row.instance_id in instances
        ]
        runs.sort(key=lambda run: run.instance_name.lower())
        built.append(
            schemas.TestExperiment(
                id=record.id,
                kind=record.kind,  # type: ignore[arg-type]
                pipeline_id=record.pipeline_id,
                variant_id=record.variant_id,
                label=record.label,
                streams=record.streams,
                max_runtime=record.max_runtime,
                fps_floor=record.fps_floor,
                created_at=record.created_at,
                state=_rollup_state(run.state for run in runs),
                runs=runs,
            )
        )
    return built


def _test_experiment_run(
    row: TestExperimentRun, instance: Instance, jobs: dict[str, dict[str, Any]]
) -> schemas.TestExperimentRun:
    job = jobs.get(row.job_id) if row.job_id else None

    if row.error:
        state = "FAILED"
    elif job is None:
        state = "UNKNOWN"
    else:
        state = str(job.get("state") or "UNKNOWN")

    return schemas.TestExperimentRun(
        instance_id=instance.id,
        instance_name=instance.name,
        cpu=instance.cpu,
        job_id=row.job_id,
        state=state,
        error=row.error,
        start_time=(job or {}).get("start_time"),
        elapsed_time=(job or {}).get("elapsed_time"),
        total_fps=(job or {}).get("total_fps"),
        per_stream_fps=(job or {}).get("per_stream_fps"),
        total_streams=(job or {}).get("total_streams"),
        ref=f"{instance.id}:{row.job_id}" if job else None,
    )


def _rollup_state(states: Iterable[str]) -> str:
    seen = set(states)
    for candidate in ("RUNNING", "FAILED", "COMPLETED"):
        if candidate in seen:
            return candidate
    return "UNKNOWN"


# --------------------------------------------------------------------------- #
# Performance / density test jobs
# --------------------------------------------------------------------------- #


def _short_pipeline_id(raw: str) -> str:
    """`/pipelines/x/variants/cpu` -> `x/cpu`; `__graph-abc123` -> `custom:abc123`."""
    if raw.startswith("/pipelines/"):
        parts = [part for part in raw.split("/") if part]
        if len(parts) >= 4:
            return f"{parts[1]}/{parts[3]}"
        return parts[-1]
    for prefix in ("__description-", "__graph-"):
        if raw.startswith(prefix):
            return f"custom:{raw.removeprefix(prefix)[:8]}"
    return raw


def _job_pipelines(job: dict[str, Any]) -> list[str]:
    return [
        _short_pipeline_id(str(entry.get("id", "")))
        for entry in job.get("streams_per_pipeline") or []
    ]


def _job_workload(job: dict[str, Any], kind: str) -> str | None:
    entries = job.get("streams_per_pipeline") or []
    if not entries:
        return None
    if kind == "density":
        return " + ".join(_short_pipeline_id(str(e.get("id", ""))) for e in entries)
    return " + ".join(
        f"{_short_pipeline_id(str(e.get('id', '')))} ×{e.get('streams')}" for e in entries
    )


async def test_jobs(session: AsyncSession, kind: str) -> list[schemas.TestJob]:
    instances = await list_instances(session, only_enabled=True)
    gathered = await _gather_per_instance(instances, lambda i: _client(i).job_statuses(kind))

    jobs: list[schemas.TestJob] = []
    for instance, payload, error in gathered:
        if error or not payload:
            continue
        for job in payload:
            jobs.append(
                schemas.TestJob(
                    **_instance_ref(instance),
                    id=job["id"],
                    kind=kind,  # type: ignore[arg-type]
                    state=job.get("state", "UNKNOWN"),
                    start_time=job.get("start_time"),
                    elapsed_time=job.get("elapsed_time"),
                    total_fps=job.get("total_fps"),
                    per_stream_fps=job.get("per_stream_fps"),
                    total_streams=job.get("total_streams"),
                    details=[str(d) for d in job.get("details") or []],
                    workload=_job_workload(job, kind),
                    pipelines=_job_pipelines(job),
                    ref=f"{instance.id}:{job['id']}",
                )
            )
    jobs.sort(key=lambda job: job.start_time or 0, reverse=True)
    return jobs


async def _job_with_spec(
    session: AsyncSession, kind: str, ref: str
) -> tuple[Instance, dict[str, Any], dict[str, Any]]:
    instance_id, job_id = parse_job_ref(ref)
    instance = await session.get(Instance, instance_id)
    if instance is None:
        raise KeyError(f"unknown instance {instance_id}")
    client = _client(instance)

    statuses, summary = await asyncio.gather(
        client.job_statuses(kind), client.job_summary(kind, job_id), return_exceptions=True
    )
    status_list = statuses if isinstance(statuses, list) else []
    job = next((entry for entry in status_list if entry.get("id") == job_id), None)
    if job is None:
        raise KeyError(f"job {job_id} not found on {instance.name}")
    spec = summary.get("request", {}) if isinstance(summary, dict) else {}
    return instance, job, spec


def _spec_pipeline_label(pipeline: dict[str, Any]) -> str:
    source = pipeline.get("source")
    if source == "variant":
        return f"{pipeline.get('pipeline_id')}/{pipeline.get('variant_id')}"
    if source == "description":
        return f"custom:{pipeline.get('description_id') or 'inline'}"
    return str(source or "pipeline")


def _spec_signature(spec: dict[str, Any], kind: str) -> tuple[str, str]:
    """Build (row key, human label) so the same test aligns across machines."""
    key_name = "pipeline_density_specs" if kind == "density" else "pipeline_performance_specs"
    parts: list[str] = []
    for entry in spec.get(key_name) or []:
        label = _spec_pipeline_label(entry.get("pipeline") or {})
        if kind == "density":
            parts.append(label)
        else:
            parts.append(f"{label} ×{entry.get('streams')}")
    if not parts:
        return ("unknown", "Unknown workload")
    label = " + ".join(sorted(parts))
    if kind == "density":
        label = f"{label} @ {spec.get('fps_floor')} fps floor"
    return (label, label)


async def compare_tests(
    session: AsyncSession, kind: str, refs: Sequence[str]
) -> schemas.Comparison:
    columns: list[schemas.ComparisonColumn] = []
    rows: dict[str, schemas.ComparisonRow] = {}
    errors: dict[str, str] = {}

    fetched = await asyncio.gather(
        *(_job_with_spec(session, kind, ref) for ref in refs), return_exceptions=True
    )

    for ref, result in zip(refs, fetched):
        if isinstance(result, BaseException):
            errors[ref] = str(result) or result.__class__.__name__
            continue
        instance, job, spec = result
        key, label = _spec_signature(spec, kind)
        if key == "unknown":
            key = _job_workload(job, kind) or job["id"]
            label = key

        columns.append(
            schemas.ComparisonColumn(
                ref=ref,
                label=f"{instance.name} · {job['id'][:8]}",
                instance_id=instance.id,
                instance_name=instance.name,
                cpu=instance.cpu,
                status=job.get("state"),
                start_time=job.get("start_time"),
                summary={
                    "total_fps": job.get("total_fps"),
                    "per_stream_fps": job.get("per_stream_fps"),
                    "total_streams": job.get("total_streams"),
                    "elapsed_time": job.get("elapsed_time"),
                },
            )
        )

        row = rows.setdefault(key, schemas.ComparisonRow(key=key, label=label))
        row.cells[ref] = {
            "status": job.get("state"),
            "total_fps": job.get("total_fps"),
            "per_stream_fps": job.get("per_stream_fps"),
            "total_streams": job.get("total_streams"),
            "elapsed_time": job.get("elapsed_time"),
            "fps_floor": spec.get("fps_floor"),
        }

    metrics = DENSITY_METRICS if kind == "density" else PERFORMANCE_METRICS
    return schemas.Comparison(
        columns=columns,
        rows=sorted(rows.values(), key=lambda row: row.label),
        metrics=metrics,
        errors=errors,
    )
