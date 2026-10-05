# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for VIPPET performance benchmark tests."""

import logging
import os
import time
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import httpx

from helpers.api_helpers import fetch_devices
from helpers.pipeline_case_helpers import (
    SUPPORTED_DEVICE_FAMILIES,
    PipelineCase,
    discover_pipeline_cases_for_pytest,
)
from perf_helpers.config import (
    BASE_URL,
    CREATE_LATEST_LINK,
    METRICS_SAMPLE_INTERVAL,
    METRICS_URL,
    ON_UNKNOWN_FILTER_ID,
    PERF_RESULTS_DIR,
    PIPELINE_FILTER,
    POLL_INTERVAL,
    POLL_TIMEOUT,
    READINESS_TIMEOUT_SECONDS,
    REQUEST_TIMEOUT,
    RESULT_FORMATS,
    SKIP_PIPELINES,
    SKIP_VARIANTS,
    STREAM_COUNTS,
    VARIANT_FILTER,
)
from perf_helpers.hw_monitor import HardwareMonitor
from perf_helpers.preflight import run_preflight_or_exit
from perf_helpers.reporters import ResultExporter, generate_html_report

logger = logging.getLogger(__name__)

# Propagate perf YAML config to env vars consumed by functional helpers.
# Only set if not already overridden by the environment.
os.environ.setdefault("VIPPET_BASE_URL", BASE_URL)
os.environ.setdefault("VIPPET_JOB_TIMEOUT_SECONDS", str(int(POLL_TIMEOUT)))
os.environ.setdefault("VIPPET_JOB_POLL_INTERVAL", str(POLL_INTERVAL))


def _collect_system_info(session: httpx.Client | None = None) -> dict[str, Any]:
    """Collect system details from VIPPET APIs for the benchmark report."""

    devices_info: dict[str, str] = {}
    if session is not None:
        try:
            devices = fetch_devices(session)  # type: ignore[arg-type]
            for device in devices:
                family = device.get("device_family", "").upper()
                full_name = device.get("full_device_name", "")
                if family and full_name:
                    devices_info[family] = full_name
        except Exception:
            logger.debug("Failed to fetch device info from VIPPET /devices API")

    system: dict[str, str] = {}
    if devices_info.get("CPU"):
        system["Processor"] = devices_info["CPU"]
    if devices_info.get("GPU"):
        system["GPU"] = devices_info["GPU"]
    if devices_info.get("NPU"):
        system["NPU"] = devices_info["NPU"]

    return {"system": system}


_QUICK_STREAM_COUNTS: set[int] = {1, 3}
_QUICK_VARIANTS: set[str] = {"CPU", "GPU"}

_PIPELINE_CASES: list[PipelineCase | object] | None = None
_CASE_IDS: list[str] | None = None


def _unwrap_case(
    case_param: PipelineCase | object,
) -> tuple[PipelineCase | None, list[pytest.Mark], bool]:
    """Return (case, skip_marks, is_skipped) for a raw or pytest.param-wrapped case."""
    if isinstance(case_param, PipelineCase):
        return case_param, [], False
    # pytest.param wrapper (ParameterSet) with .values and .marks attrs
    wrapped: Any = case_param
    actual_case = wrapped.values[0]
    skip_marks = list(wrapped.marks)
    is_skipped = any(m.name == "skip" for m in skip_marks)
    return actual_case, skip_marks, is_skipped


def _validate_filter_ids(
    cases: list[PipelineCase | object],
) -> list[PipelineCase | object]:
    """Diff configured filter ids against discovered ids.

    Returns synthetic skipped entries for unknown ids when
    ``ON_UNKNOWN_FILTER_ID == "warn"``. Aborts the session via
    ``pytest.exit`` when it is ``"fail"`` (the default), naming every
    bad id and its valid alternatives.
    """
    valid_pipeline_ids = sorted(
        {c.pipeline_id for cp in cases for c, _, _ in [_unwrap_case(cp)] if c}
    )
    valid_pipeline_ids_lower = {p.lower() for p in valid_pipeline_ids}

    issues: list[tuple[str, str, list[str]]] = []

    if PIPELINE_FILTER != "*":
        requested = (
            PIPELINE_FILTER if isinstance(PIPELINE_FILTER, list) else [PIPELINE_FILTER]
        )
        for pid in requested:
            if pid not in valid_pipeline_ids:
                issues.append(("benchmark.pipelines", pid, valid_pipeline_ids))

    for pid in SKIP_PIPELINES:
        if pid.lower() not in valid_pipeline_ids_lower:
            issues.append(("benchmark.filters.skip_pipelines", pid, valid_pipeline_ids))

    for variant in SKIP_VARIANTS:
        if variant.upper() not in SUPPORTED_DEVICE_FAMILIES:
            issues.append(
                (
                    "benchmark.filters.skip_variants",
                    variant,
                    sorted(SUPPORTED_DEVICE_FAMILIES),
                )
            )

    for variant in VARIANT_FILTER:
        if variant.upper() not in SUPPORTED_DEVICE_FAMILIES:
            issues.append(
                ("benchmark.variants", variant, sorted(SUPPORTED_DEVICE_FAMILIES))
            )

    if not issues:
        return []

    lines = [
        f"Unknown id {bad_id!r} in {field}. Valid ids: {valid}"
        for field, bad_id, valid in issues
    ]
    message = "Invalid performance filter configuration:\n" + "\n".join(lines)

    if ON_UNKNOWN_FILTER_ID == "fail":
        pytest.exit(message, returncode=4)

    logger.warning(message)
    synthetic: list[PipelineCase | object] = []
    for field, bad_id, _valid in issues:
        reason = f"Unknown id {bad_id!r} in {field}; see log for valid ids."
        bad_case = PipelineCase(
            case_id=f"invalid_{field.rsplit('.', 1)[-1]}_{bad_id}",
            pipeline_id=bad_id,
            variant_id="",
            device_family="UNKNOWN",
            pipeline_name=bad_id,
        )
        synthetic.append(pytest.param(bad_case, marks=pytest.mark.skip(reason=reason)))
    return synthetic


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart() -> None:
    """Verify ViPPET readiness once before performance test collection."""
    run_preflight_or_exit(
        BASE_URL,
        READINESS_TIMEOUT_SECONDS,
        POLL_INTERVAL,
        REQUEST_TIMEOUT,
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate the cross-product parametrization: pipeline_case x stream_count."""
    global _PIPELINE_CASES, _CASE_IDS

    if (
        "pipeline_case" not in metafunc.fixturenames
        or "stream_count" not in metafunc.fixturenames
    ):
        return

    if _PIPELINE_CASES is None or _CASE_IDS is None:
        _PIPELINE_CASES, _CASE_IDS = discover_pipeline_cases_for_pytest()

    for invalid_param in _validate_filter_ids(_PIPELINE_CASES):
        invalid_case, _, _ = _unwrap_case(invalid_param)
        if invalid_case is None:
            continue
        _PIPELINE_CASES.append(invalid_param)
        _CASE_IDS.append(invalid_case.case_id)

    params = []
    ids = []

    _allowed_variants = {v.upper() for v in VARIANT_FILTER}
    _skip_pipelines = {p.lower() for p in SKIP_PIPELINES}
    _skip_variants = {v.upper() for v in SKIP_VARIANTS}

    for case_param, case_id in zip(_PIPELINE_CASES, _CASE_IDS):
        actual_case, skip_marks, is_skipped = _unwrap_case(case_param)

        if not is_skipped and actual_case is not None:
            # Apply pipeline filter from config
            if PIPELINE_FILTER != "*":
                allowed_ids = (
                    PIPELINE_FILTER
                    if isinstance(PIPELINE_FILTER, list)
                    else [PIPELINE_FILTER]
                )
                if actual_case.pipeline_id not in allowed_ids:
                    continue

            # Apply skip lists
            if actual_case.pipeline_id.lower() in _skip_pipelines:
                continue

            device_family = actual_case.device_family.upper()
            variant_parts = set(device_family.split("_"))

            if device_family in _skip_variants:
                continue

            # Apply variant filter — all parts must be in allowed variants
            if not variant_parts <= _allowed_variants:
                continue

        for streams in STREAM_COUNTS:
            marks: list[Any] = [pytest.mark.perf]
            marks.extend(skip_marks)

            if not is_skipped and actual_case is not None:
                device_family = actual_case.device_family.upper()
                variant_families = set(device_family.split("_"))
                is_quick = (
                    variant_families <= _QUICK_VARIANTS
                    and streams in _QUICK_STREAM_COUNTS
                )
                if is_quick:
                    marks.append(pytest.mark.perf_quick)
                marks.append(pytest.mark.perf_full)

            params.append(pytest.param(case_param, streams, marks=marks))
            ids.append(f"{case_id}_x{streams}")

    metafunc.parametrize(["pipeline_case", "stream_count"], params, ids=ids)


@pytest.fixture(scope="session")
def http_client() -> Generator[httpx.Client, None, None]:
    """Reusable HTTP client for all performance tests."""
    client = httpx.Client(
        headers={"Accept": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    yield client
    client.close()


@pytest.fixture
def hw_monitor() -> HardwareMonitor:
    """Create a HardwareMonitor instance for per-test HW sampling."""
    return HardwareMonitor(METRICS_URL, METRICS_SAMPLE_INTERVAL)


@pytest.fixture(scope="session")
def results_collector(
    request: pytest.FixtureRequest, http_client: httpx.Client
) -> list[dict[str, Any]]:
    """Session-scoped accumulator that exports results on teardown."""
    results: list[dict[str, Any]] = []
    start_time = time.time()

    def _finalize() -> None:
        if not results:
            return
        total_duration = time.time() - start_time
        benchmark_id = f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = Path(PERF_RESULTS_DIR) / benchmark_id
        exporter = ResultExporter(output_dir, formats=RESULT_FORMATS)

        system_info = _collect_system_info(http_client)

        hw_families: dict[str, list[str]] = {}
        for r in results:
            family = r.get("variant_name", "").upper()
            for part in family.split("_"):
                if part in {"CPU", "GPU", "NPU"}:
                    hw_families.setdefault(part, [])
                    device_name = system_info.get("system", {}).get(
                        part if part != "CPU" else "Processor", ""
                    )
                    if device_name and device_name not in hw_families[part]:
                        hw_families[part].append(device_name)

        n_skipped = sum(1 for r in results if r["status"] == "skipped")
        result_dict: dict[str, Any] = {
            "benchmark_id": benchmark_id,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": total_duration,
            "test_cases": results,
            "summary": {
                "total": len(results),
                "success": sum(1 for r in results if r["status"] == "success"),
                "failed": sum(1 for r in results if r["status"] == "failed"),
                "skipped": n_skipped,
            },
            "hardware": hw_families,
            "system_info": system_info,
        }
        exporter.export(result_dict)
        html_content = generate_html_report([result_dict])
        html_path = output_dir / f"{benchmark_id}.html"
        html_path.write_text(html_content)
        logger.info("Performance report: %s", html_path)

        if CREATE_LATEST_LINK:
            latest_link = Path(PERF_RESULTS_DIR) / "latest"
            latest_link.unlink(missing_ok=True)
            latest_link.symlink_to(output_dir.name)
            logger.info("Latest results symlink: %s", latest_link)

    request.addfinalizer(_finalize)
    return results


_RESULTS_COLLECTOR_REF: list[list[dict[str, Any]]] = []


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:  # type: ignore[type-arg]
    """Capture skipped perf tests into the results collector."""
    if call.when != "setup":
        return
    if call.excinfo is None:
        return
    if not call.excinfo.errisinstance(pytest.skip.Exception):
        return
    if not any(m.name == "perf" for m in item.iter_markers()):
        return

    callspec = getattr(item, "callspec", None)
    if callspec is None:
        return
    params = callspec.params
    case_param = params.get("pipeline_case")
    stream_count = params.get("stream_count", 0)

    actual_case: PipelineCase | None = None
    if isinstance(case_param, PipelineCase):
        actual_case = case_param
    elif case_param is not None:
        wrapped: Any = case_param
        vals = getattr(wrapped, "values", None)
        if vals:
            actual_case = vals[0]

    skip_reason = str(call.excinfo.value)

    entry = {
        "pipeline_name": actual_case.pipeline_name if actual_case else "unknown",
        "pipeline_id": actual_case.pipeline_id if actual_case else "",
        "variant_name": actual_case.device_family if actual_case else "",
        "variant_id": actual_case.variant_id if actual_case else "",
        "streams": stream_count,
        "status": "skipped",
        "total_fps": None,
        "per_stream_fps": None,
        "result": None,
        "hw_metrics": {"sample_count": 0},
        "duration_seconds": 0,
        "job_id": "",
        "error": skip_reason,
    }

    if _RESULTS_COLLECTOR_REF:
        _RESULTS_COLLECTOR_REF[0].append(entry)


@pytest.fixture(autouse=True, scope="session")
def _bind_results_ref(results_collector: list[dict[str, Any]]) -> None:
    """Bind the results_collector list to the module-level ref for the skip hook."""
    _RESULTS_COLLECTOR_REF.clear()
    _RESULTS_COLLECTOR_REF.append(results_collector)
