# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for VIPPET performance benchmark tests."""

import logging
import platform
import subprocess
import time
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import requests

from helpers.api_helpers import fetch_devices
from helpers.pipeline_case_helpers import (
    PipelineCase,
    discover_pipeline_cases_for_pytest,
)
from perf_helpers.config import (
    CREATE_LATEST_LINK,
    METRICS_SAMPLE_INTERVAL,
    METRICS_URL,
    PERF_RESULTS_DIR,
    RESULT_FORMATS,
    STREAM_COUNTS,
)
from helpers.config import BASE_URL
from perf_helpers.hw_monitor import HardwareMonitor
from perf_helpers.reporters import ResultExporter, generate_html_report

logger = logging.getLogger(__name__)


def _collect_system_info(session: requests.Session | None = None) -> dict[str, Any]:
    """Collect system details for the benchmark report."""

    def _cmd(args: list[str]) -> str:
        try:
            return subprocess.check_output(
                args, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            return ""

    cpu_model = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu_model = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass

    os_name = ""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    os_name = line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass

    mem_capacity = ""
    try:
        for line in _cmd(["free", "-h", "--si"]).split("\n"):
            if line.startswith("Mem:"):
                mem_capacity = line.split()[1]
                break
    except Exception:
        pass

    vippet_version = ""
    try:
        resp = requests.get(f"{BASE_URL}/version", timeout=5)
        if resp.ok:
            data = resp.json()
            vippet_version = data.get("version", str(data))
    except Exception:
        pass
    if not vippet_version:
        tag = _cmd(["docker", "inspect", "--format", "{{.Config.Image}}", "vippet"])
        if ":" in tag:
            vippet_version = tag.split(":", 1)[1]

    devices_info: dict[str, str] = {}
    if session is not None:
        try:
            devices = fetch_devices(session)
            for device in devices:
                family = device.get("device_family", "").upper()
                name = device.get("name") or device.get("device_name", "")
                if family and name:
                    devices_info[family] = name
                elif family:
                    devices_info[family] = "detected"
        except Exception:
            logger.debug("Failed to fetch device info for system_info")

    system: dict[str, str] = {
        "Processor": cpu_model,
        "Memory": mem_capacity,
        "OS": os_name,
        "Kernel": platform.release(),
    }
    if devices_info.get("GPU"):
        system["GPU"] = devices_info["GPU"]
    if devices_info.get("NPU"):
        system["NPU"] = devices_info["NPU"]

    return {
        "system": system,
        "software": {
            "VIPPET": vippet_version,
        },
    }


_QUICK_STREAM_COUNTS: set[int] = {1, 3}
_QUICK_VARIANTS: set[str] = {"CPU", "GPU"}

_PIPELINE_CASES, _CASE_IDS = discover_pipeline_cases_for_pytest()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate the cross-product parametrization: pipeline_case x stream_count."""
    if (
        "pipeline_case" not in metafunc.fixturenames
        or "stream_count" not in metafunc.fixturenames
    ):
        return

    params = []
    ids = []

    for case_param, case_id in zip(_PIPELINE_CASES, _CASE_IDS):
        actual_case: PipelineCase | None = None
        is_skipped = False
        skip_marks: list[pytest.Mark] = []

        if isinstance(case_param, PipelineCase):
            actual_case = case_param
        else:
            # pytest.param wrapper (ParameterSet) with .values and .marks attrs
            wrapped: Any = case_param
            actual_case = wrapped.values[0]
            skip_marks = list(wrapped.marks)
            is_skipped = any(m.name == "skip" for m in skip_marks)

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
def http_client() -> Generator[requests.Session, None, None]:
    """Reusable HTTP session for all performance tests."""
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    yield session
    session.close()


@pytest.fixture
def hw_monitor() -> HardwareMonitor:
    """Create a HardwareMonitor instance for per-test HW sampling."""
    return HardwareMonitor(METRICS_URL, METRICS_SAMPLE_INTERVAL)


@pytest.fixture(scope="session")
def results_collector(
    request: pytest.FixtureRequest, http_client: requests.Session
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
