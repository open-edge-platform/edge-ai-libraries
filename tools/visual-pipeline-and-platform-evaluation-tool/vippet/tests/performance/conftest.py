# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for VIPPET performance benchmark tests.

Console output of a normal run, in order: ViPPET readiness -> discovered
hardware -> benchmark matrix -> per-test status -> pytest summary ->
benchmark artefacts.
"""

import contextlib
import dataclasses
import logging
import httpx
import os
import sys
import time
import pytest
from collections.abc import Callable, Generator
from datetime import datetime
from pathlib import Path
from typing import Any

from dataclasses import dataclass, field
from helpers.pipeline_case_helpers import PipelineCase
from perf_helpers.hw_monitor import HardwareMonitor
from perf_helpers.job_outcome import describe_missing_hw_samples
from perf_helpers.preflight import (
    describe_discovery_error,
    fetch_capabilities,
    fetch_discovered_devices,
    fetch_vippet_version,
    format_discovered_hardware,
    run_preflight_or_exit,
)
from perf_helpers.reporters import ResultExporter, generate_html_report
from perf_helpers.settings import SettingsError

try:
    from perf_helpers.config import (
        BASE_URL,
        CAPABILITIES_URL,
        CREATE_LATEST_LINK,
        METRICS_SAMPLE_INTERVAL,
        METRICS_URL,
        ON_UNKNOWN_FILTER_ID,
        PERF_RESULTS_DIR,
        POLL_INTERVAL,
        POLL_TIMEOUT,
        READINESS_TIMEOUT_SECONDS,
        REQUEST_TIMEOUT,
        RESULT_FORMATS,
        SKIP_MISSING_MODELS,
        SETTINGS,
        STREAM_COUNTS,
    )
except SettingsError as exc:
    # Same message and exit code (2) as the CLI instead of a traceback.
    # pytest.exit() cannot be used here: pytest wraps any Exception raised
    # while importing a conftest (including pytest's Exit) into a
    # ConftestImportFailure and prints a traceback with exit code 4.
    # SystemExit is a BaseException and is not wrapped.
    print(f"error: invalid performance config: {exc}", file=sys.stderr)
    raise SystemExit(2) from None

# Propagate perf config to env vars consumed by functional helpers. This must
# run BEFORE importing ``helpers.*``: helpers.config reads these env vars once
# at import time. These keys are env-backed in perf_helpers.settings, so an
# already-exported value is what BASE_URL/POLL_* resolved to; setdefault only
# fills in YAML/default values.
os.environ.setdefault("VIPPET_BASE_URL", BASE_URL)
os.environ.setdefault("VIPPET_JOB_TIMEOUT_SECONDS", str(POLL_TIMEOUT))
os.environ.setdefault("VIPPET_JOB_POLL_INTERVAL", str(POLL_INTERVAL))

from helpers.pipeline_case_helpers import wrap_cases_for_pytest  # noqa: E402
from perf_helpers.discovery import discover_matrix  # noqa: E402
from perf_helpers.matrix import (  # noqa: E402
    Matrix,
    MatrixFilters,
    describe_no_cases,
    describe_unknown_filter_ids,
    find_unknown_filter_ids,
    format_matrix,
)
from perf_helpers.system_info import collect_system_info  # noqa: E402

logger = logging.getLogger(__name__)

# Exit code for invalid filter ids (pytest's "usage error").
_INVALID_FILTER_EXIT_CODE = 4

# Snapshot of GET /devices, GET /api/v1/capabilities and GET /status captured
# once at pre-flight time (see pytest_sessionstart below). Populated
# independent of any test outcome so a fully failed/skipped run still has
# the discovered hardware/platform info available for the report.
_DISCOVERED_DEVICES: list[dict[str, Any]] = []
_CAPABILITIES: dict[str, Any] = {}
_VIPPET_VERSION: str = "Unknown"

# Filled by the results_collector finalizer and printed by
# pytest_terminal_summary: written files, why nothing was written, and a
# warning when no hardware metrics were sampled.
_ARTEFACTS: list[tuple[str, Path]] = []
_ARTEFACT_ERROR: str | None = None
_HW_WARNING: str | None = None

# Unknown filter ids found while parametrizing: (explanation, is_fatal).
# Reported after the matrix; a fatal one then ends the session from
# pytest_collection_finish, because pytest turns an Exit raised inside
# pytest_generate_tests into a collection error with a traceback.
_FILTER_PROBLEM: tuple[str, bool] | None = None


_QUICK_STREAM_COUNTS: set[int] = {1, 3}
_QUICK_VARIANTS: set[str] = {"CPU", "GPU"}

# Loggers whose per-request INFO lines ("HTTP Request: GET ...") only repeat
# what the [pre-flight] lines and helpers.api_helpers already report. With
# --log-cli-level=INFO they would be printed inline and split the console
# sections, so only their warnings and errors are kept.
_NOISY_LOGGERS: tuple[str, ...] = ("httpx", "httpcore")


def pytest_configure(config: pytest.Config) -> None:
    """Keep per-request HTTP client logs out of the console and reports."""
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


# --------------------------------------------------------------------------- #
# Console output
# --------------------------------------------------------------------------- #


def _uncaptured(config: pytest.Config) -> contextlib.AbstractContextManager[Any]:
    capman = config.pluginmanager.get_plugin("capturemanager")
    return capman.global_and_fixture_disabled() if capman else contextlib.nullcontext()


def _console(config: pytest.Config, **markup: bool) -> Callable[[str], None]:
    """Return a writer that reaches the terminal even while pytest captures
    output (e.g. during collection). Multi-line text is written line by line."""
    terminal = config.pluginmanager.get_plugin("terminalreporter")

    def write(text: str) -> None:
        with _uncaptured(config):
            for line in text.splitlines() or [""]:
                if terminal is not None:
                    terminal.write_line(line, **markup)
                else:
                    stream = sys.stderr if markup else sys.stdout
                    print(line, file=stream, flush=True)

    return write


def _error_console(config: pytest.Config) -> Callable[[str], None]:
    write = _console(config, red=True, bold=True)
    return lambda message: write(f"error: {message}")


def _section(config: pytest.Config, title: str) -> None:
    terminal = config.pluginmanager.get_plugin("terminalreporter")
    with _uncaptured(config):
        if terminal is not None:
            terminal.write_sep("-", title)
        else:
            print(f"--- {title} ---", flush=True)


@dataclass
class _DiscoveredCases:
    """Cached, one-time result of :func:`_discover_case_params`.

    * ``params``/``case_ids`` - the actual pytest parameter values (and
      their matching string ids) for the ``pipeline_case`` fixture,
      *after* all config/host filtering. This is what actually runs.
    * ``known_pipeline_ids`` - every pipeline id the API reports to
      exist, *before* any ``pipelines``/``skip_pipelines`` filtering.
      Used to validate user-supplied filter ids.
    * ``matrix`` - the matrix printed after collection; ``None`` when
      discovery failed, in which case ``error`` explains why.
    """

    params: list[PipelineCase | object]
    case_ids: list[str]
    known_pipeline_ids: list[str]
    matrix: Matrix | None = None
    error: str | None = None
    validated: bool = field(default=False)


_DISCOVERED_CASES: _DiscoveredCases | None = None


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
    config: pytest.Config, known_pipeline_ids: list[str]
) -> list[PipelineCase | object]:
    """Diff configured filter ids against discovered ids.

    Returns synthetic skipped entries for unknown ids when
    ``ON_UNKNOWN_FILTER_ID == "warn"``. When it is ``"fail"`` (the default)
    no cases are added and the session is aborted once collection has
    finished (see ``pytest_collection_finish``). Either way the explanation
    is kept in ``_FILTER_PROBLEM`` and printed after the matrix.
    """
    global _FILTER_PROBLEM
    issues = find_unknown_filter_ids(
        MatrixFilters.from_settings(SETTINGS), known_pipeline_ids
    )
    if not issues:
        return []

    message = describe_unknown_filter_ids(issues, SETTINGS.config_path)
    _FILTER_PROBLEM = (message, ON_UNKNOWN_FILTER_ID == "fail")
    if ON_UNKNOWN_FILTER_ID == "fail":
        return []

    synthetic: list[PipelineCase | object] = []
    for issue in issues:
        reason = (
            f"{issue.describe()}. To fix: correct or remove it in "
            f"{SETTINGS.config_path} or {issue.flag}."
        )
        bad_case = PipelineCase(
            case_id=f"invalid_{issue.key.rsplit('.', 1)[-1]}_{issue.value}",
            pipeline_id=issue.value,
            variant_id="",
            device_family="UNKNOWN",
            pipeline_name=issue.value,
        )
        synthetic.append(pytest.param(bad_case, marks=pytest.mark.skip(reason=reason)))
    return synthetic


@pytest.hookimpl(wrapper=True)
def pytest_sessionstart(session: pytest.Session) -> Generator[None, None, None]:
    """Verify ViPPET readiness and capture its hardware/platform snapshot once.

    Runs after pytest has printed its own header. Fixtures (e.g.
    ``http_client``) aren't available yet at this point in the pytest
    lifecycle, so the pre-flight phase opens and owns its own client.
    """
    global _DISCOVERED_DEVICES, _CAPABILITIES, _VIPPET_VERSION
    result = yield
    config = session.config
    write = _console(config)

    _section(config, "ViPPET readiness")
    with httpx.Client(headers={"Accept": "application/json"}) as client:
        run_preflight_or_exit(
            BASE_URL,
            READINESS_TIMEOUT_SECONDS,
            POLL_INTERVAL,
            REQUEST_TIMEOUT,
            client=client,
            report=write,
            report_error=_error_console(config),
        )
        _DISCOVERED_DEVICES = fetch_discovered_devices(
            BASE_URL, REQUEST_TIMEOUT, client=client, report=write
        )
        _CAPABILITIES = fetch_capabilities(
            CAPABILITIES_URL, REQUEST_TIMEOUT, client=client, report=write
        )
        _VIPPET_VERSION = fetch_vippet_version(
            BASE_URL, REQUEST_TIMEOUT, client=client, report=write
        )

    _section(config, "Discovered hardware")
    for line in format_discovered_hardware(_DISCOVERED_DEVICES, _VIPPET_VERSION):
        write(line)
    return result


def _discover_case_params() -> _DiscoveredCases:
    """Build the filtered matrix and wrap it for ``pytest.mark.parametrize``.

    Filtering (pipelines / variants / skip lists / host families) is done by
    :func:`perf_helpers.matrix.build_matrix`; missing-model handling stays in
    :func:`wrap_cases_for_pytest`.
    """
    try:
        matrix = discover_matrix(MatrixFilters.from_settings(SETTINGS))
    except Exception as exc:
        reason = describe_discovery_error(exc, BASE_URL)
        logger.debug("Inventory discovery failed", exc_info=True)
        skip = pytest.mark.skip(reason=reason)
        return _DiscoveredCases(
            [pytest.param(None, marks=skip)], ["no-cases"], [], error=reason
        )

    if not matrix.included:
        skip = pytest.mark.skip(reason=describe_no_cases(matrix))
        return _DiscoveredCases(
            [pytest.param(None, marks=skip)],
            ["no-cases"],
            matrix.known_pipeline_ids,
            matrix=matrix,
        )

    cases = [PipelineCase(**dataclasses.asdict(case)) for case in matrix.included]
    missing = {pid: set(models) for pid, models in matrix.missing_models.items()}
    params, ids = wrap_cases_for_pytest(
        cases, missing, skip_missing_models=SKIP_MISSING_MODELS
    )
    return _DiscoveredCases(params, ids, matrix.known_pipeline_ids, matrix=matrix)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate the cross-product parametrization: pipeline_case x stream_count."""
    global _DISCOVERED_CASES

    if (
        "pipeline_case" not in metafunc.fixturenames
        or "stream_count" not in metafunc.fixturenames
    ):
        return

    if _DISCOVERED_CASES is None:
        _DISCOVERED_CASES = _discover_case_params()

    # Without a discovered inventory every id would look unknown, so only
    # validate filter ids against a real matrix, and only once.
    if _DISCOVERED_CASES.matrix is not None and not _DISCOVERED_CASES.validated:
        _DISCOVERED_CASES.validated = True
        for invalid_param in _validate_filter_ids(
            metafunc.config, _DISCOVERED_CASES.known_pipeline_ids
        ):
            invalid_case, _, _ = _unwrap_case(invalid_param)
            if invalid_case is None:
                continue
            _DISCOVERED_CASES.params.append(invalid_param)
            _DISCOVERED_CASES.case_ids.append(invalid_case.case_id)

    params = []
    ids = []

    for case_param, case_id in zip(
        _DISCOVERED_CASES.params, _DISCOVERED_CASES.case_ids
    ):
        actual_case, skip_marks, is_skipped = _unwrap_case(case_param)

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


@pytest.hookimpl(trylast=True)
def pytest_collection_finish(session: pytest.Session) -> None:
    """End the session cleanly when parametrization found invalid filter ids.

    ``trylast`` so the matrix (printed by the terminal reporter's own
    collection-finish hook) comes first and the error is the last thing shown.
    """
    if _FILTER_PROBLEM is not None and _FILTER_PROBLEM[1]:
        _error_console(session.config)(_FILTER_PROBLEM[0])
        pytest.exit(
            "Invalid benchmark filter ids (see the error above)",
            returncode=_INVALID_FILTER_EXIT_CODE,
        )


def pytest_report_collectionfinish(
    config: pytest.Config, start_path: Path, items: list[pytest.Item]
) -> list[str]:
    """Print the benchmark matrix (or why there is none) right after collection."""
    if _DISCOVERED_CASES is None:
        return []
    _section(config, "Benchmark matrix")
    if _DISCOVERED_CASES.matrix is None:
        _error_console(config)(_DISCOVERED_CASES.error or "matrix not available")
        return []
    write = _console(config)
    write(
        format_matrix(_DISCOVERED_CASES.matrix, skip_missing_models=SKIP_MISSING_MODELS)
    )
    if not _DISCOVERED_CASES.matrix.included:
        _console(config, yellow=True)(
            f"note: {describe_no_cases(_DISCOVERED_CASES.matrix)}"
        )
    if _FILTER_PROBLEM is not None and not _FILTER_PROBLEM[1]:
        _console(config, yellow=True)(f"warning: {_FILTER_PROBLEM[0]}")
    return []


def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: pytest.Config
) -> None:
    """List the written report files (or explain why there are none)."""
    if _DISCOVERED_CASES is None or config.getoption("collectonly", False):
        return
    nothing_to_show = not (_ARTEFACTS or _ARTEFACT_ERROR or _HW_WARNING)
    if nothing_to_show and exitstatus not in (
        pytest.ExitCode.OK,
        pytest.ExitCode.TESTS_FAILED,
    ):
        return  # aborted or nothing collected; the reason is already shown
    tr = terminalreporter
    tr.section("Benchmark artefacts", sep="-")
    if _HW_WARNING:
        tr.write_line(f"warning: {_HW_WARNING}", yellow=True)
    if _ARTEFACTS:
        width = max(len(label) for label, _ in _ARTEFACTS)
        for label, path in _ARTEFACTS:
            tr.write_line(f"{label:<{width}}  {path}")
    if _ARTEFACT_ERROR:
        tr.write_line(f"error: {_ARTEFACT_ERROR}", red=True, bold=True)
    if not (_ARTEFACTS or _ARTEFACT_ERROR):
        tr.write_line(
            "No reports were written because no benchmark result records "
            "were produced (see the failures, skips or deselections above)."
        )


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
    """Session-scoped accumulator that exports results on teardown.

    Depends on ``http_client`` only to order teardown: this fixture's
    finalizer must run while the client is still open, in case future
    report steps need live API access.
    """
    results: list[dict[str, Any]] = []
    start_time = time.time()

    def _finalize() -> None:
        global _ARTEFACT_ERROR, _HW_WARNING
        if not results:
            return
        _HW_WARNING = describe_missing_hw_samples(results, METRICS_URL)
        total_duration = time.time() - start_time
        benchmark_id = f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = Path(PERF_RESULTS_DIR) / benchmark_id

        system_info = collect_system_info(
            _DISCOVERED_DEVICES, _CAPABILITIES, _VIPPET_VERSION
        )

        # Built from the /devices snapshot captured at pre-flight, independent
        # of per-test outcomes, so a fully failed/skipped run still records
        # the discovered hardware. Per-row variant association (variant_name,
        # hw_metrics) in `results` is untouched.
        hw_families: dict[str, list[str]] = {}
        for device in _DISCOVERED_DEVICES:
            family = str(device.get("device_family", "")).upper()
            if family not in {"CPU", "GPU", "NPU"}:
                continue
            full_name = device.get("full_device_name", "")
            if full_name and full_name not in hw_families.setdefault(family, []):
                hw_families[family].append(full_name)

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
        try:
            exporter = ResultExporter(output_dir, formats=RESULT_FORMATS)
            exporter.export(result_dict)
            _ARTEFACTS.append(("Directory", output_dir))
            _ARTEFACTS.extend(
                (fmt.upper(), output_dir / f"{benchmark_id}.{fmt}")
                for fmt in RESULT_FORMATS
            )
            html_content = generate_html_report([result_dict])
            html_path = output_dir / f"{benchmark_id}.html"
            html_path.write_text(html_content)
            _ARTEFACTS.append(("HTML report", html_path))
            logger.info("Performance report: %s", html_path)

            if CREATE_LATEST_LINK:
                latest_link = Path(PERF_RESULTS_DIR) / "latest"
                latest_link.unlink(missing_ok=True)
                latest_link.symlink_to(output_dir.name)
                _ARTEFACTS.append(("Latest link", latest_link))
                logger.info("Latest results symlink: %s", latest_link)
        except OSError as exc:
            written = (
                " The files listed above were written before the failure."
                if _ARTEFACTS
                else ""
            )
            _ARTEFACT_ERROR = (
                f"Writing the benchmark reports to {output_dir} failed "
                f"({type(exc).__name__}: {exc}).{written} To fix: point "
                "--results-dir / PERF_RESULTS_DIR at a writable directory (or "
                "pass --no-latest-link if the file system has no symlinks), "
                "then rerun."
            )
            raise

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
