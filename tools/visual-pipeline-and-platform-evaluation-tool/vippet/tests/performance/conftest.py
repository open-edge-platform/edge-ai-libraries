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
import yaml

from helpers.pipeline_case_helpers import (
    PipelineCase,
    discover_pipeline_cases_for_pytest,
)
from perf_helpers.config import (
    CONFIG_DIR,
    METRICS_SAMPLE_INTERVAL,
    METRICS_URL,
    PERF_CONFIG,
    PERF_RESULTS_DIR,
)
from helpers.config import BASE_URL
from perf_helpers.hw_monitor import HardwareMonitor
from perf_helpers.reporters import ResultExporter, generate_html_report

logger = logging.getLogger(__name__)


def _collect_system_info() -> dict[str, Any]:
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

    return {
        "system": {
            "Processor": cpu_model,
            "Memory": mem_capacity,
            "OS": os_name,
            "Kernel": platform.release(),
        },
        "software": {
            "VIPPET": vippet_version,
        },
    }


def _load_perf_config() -> dict[str, Any]:
    """Load the performance config YAML selected by PERF_CONFIG env var."""
    config_path = CONFIG_DIR / f"{PERF_CONFIG}.yaml"
    if not config_path.exists():
        config_path = CONFIG_DIR / "default.yaml"
    with config_path.open() as f:
        return yaml.safe_load(f)


_PERF_YAML = _load_perf_config()
_STREAM_COUNTS: list[int] = _PERF_YAML.get("benchmark", {}).get("stream_counts", [1, 3])
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

        for streams in _STREAM_COUNTS:
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
def results_collector(request: pytest.FixtureRequest) -> list[dict[str, Any]]:
    """Session-scoped accumulator that exports results on teardown."""
    results: list[dict[str, Any]] = []
    start_time = time.time()

    def _finalize() -> None:
        if not results:
            return
        total_duration = time.time() - start_time
        benchmark_id = f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = Path(PERF_RESULTS_DIR) / benchmark_id
        exporter = ResultExporter(output_dir)
        result_dict: dict[str, Any] = {
            "benchmark_id": benchmark_id,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": total_duration,
            "test_cases": results,
            "summary": {
                "total": len(results),
                "success": sum(1 for r in results if r["status"] == "success"),
                "failed": sum(1 for r in results if r["status"] == "failed"),
                "skipped": sum(1 for r in results if r["status"] == "skipped"),
            },
            "system_info": _collect_system_info(),
        }
        exporter.export(result_dict)
        html_content = generate_html_report([result_dict])
        html_path = output_dir / f"{benchmark_id}.html"
        html_path.write_text(html_content)
        logger.info("Performance report: %s", html_path)

    request.addfinalizer(_finalize)
    return results
