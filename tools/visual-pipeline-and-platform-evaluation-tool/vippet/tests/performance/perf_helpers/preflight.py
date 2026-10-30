# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ViPPET reachability and readiness checks for performance tests.

Every message that can end a run explains what happened, why, and what to
change ("To fix: ..."), naming the exact flag or env var.
"""

import sys
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import httpx
import pytest

from .matrix import SUPPORTED_DEVICE_FAMILIES

FATAL_PREFLIGHT_EXIT_CODE = 2
FATAL_PREFLIGHT_EXIT_REASON = "ViPPET pre-flight failed (see the error above)"


class PreflightError(RuntimeError):
    """Raised when ViPPET cannot become ready for performance discovery."""


def _remaining_timeout(
    deadline: float,
    request_timeout: float,
    monotonic: Callable[[], float],
) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise PreflightError(
            "the readiness time budget (--readiness-timeout) was used up "
            "before the request could be sent"
        )
    return min(request_timeout, remaining)


def _unreachable_message(health_url: str, base_url: str, observed: str) -> str:
    return (
        f"Cannot reach ViPPET at {health_url} ({observed}). Either ViPPET is "
        "not running, or the base URL points at the wrong host or port. "
        "To fix: start ViPPET (for example 'make run', then check "
        "'docker compose ps'), or set --base-url / VIPPET_BASE_URL to the "
        f"right address (currently {base_url})."
    )


def _server_error_message(health_url: str, status_code: int) -> str:
    return (
        f"{health_url} answered with HTTP {status_code}. Something is "
        "listening at that address, but ViPPET (or the proxy in front of it) "
        "failed to handle the request - usually because the ViPPET backend "
        "is down, restarting or crashed. To fix: check 'docker compose ps' "
        "and 'docker compose logs vippet', then rerun."
    )


def _wrong_service_message(health_url: str, observed: str) -> str:
    return (
        f"{health_url} answered, but not like the ViPPET API ({observed}), "
        "so the base URL most likely points at a different service or path. "
        "To fix: set --base-url / VIPPET_BASE_URL to the ViPPET API root, "
        "which ends in /api/v1 (for example http://localhost/api/v1)."
    )


def _health_failure_message(
    exc: Exception, health_url: str, base_url: str, observed: str
) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code >= 500:
            return _server_error_message(health_url, status_code)
        return _wrong_service_message(health_url, f"HTTP {status_code}")
    if isinstance(exc, ValueError):  # includes JSON decode errors
        return _wrong_service_message(health_url, observed)
    return _unreachable_message(health_url, base_url, observed)


def _not_ready_message(
    base_url: str, status_url: str, timeout_seconds: float, last_observed: str
) -> str:
    return (
        f"ViPPET at {base_url} is reachable but did not report ready within "
        f"{timeout_seconds:g}s; the last {status_url} response was: "
        f"{last_observed}. ViPPET is most likely still starting up (for "
        "example loading models or discovering devices). To fix: wait until "
        "it finishes and rerun, or allow more time with --readiness-timeout "
        f"(currently {timeout_seconds:g}s)."
    )


def _state_description(payload: dict[str, Any]) -> str:
    return (
        f"status={payload.get('status', 'unknown')!r}, "
        f"ready={payload.get('ready', 'missing')!r}, "
        f"message={payload.get('message')!r}"
    )


def _get_json_object(
    client: httpx.Client, url: str, timeout: float
) -> tuple[httpx.Response, dict[str, Any]]:
    response = client.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"expected an object, got {type(payload).__name__}")
    return response, payload


def wait_for_vippet_ready(
    base_url: str,
    readiness_timeout_seconds: float,
    poll_interval: float,
    request_timeout: float,
    *,
    client: httpx.Client,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    report: Callable[[str], None] = print,
) -> None:
    """Check ViPPET health and wait for its status endpoint to report ready.

    *client* is owned by the caller (opened and closed there); this function
    never closes it.
    """
    health_url = f"{base_url.rstrip('/')}/health"
    status_url = f"{base_url.rstrip('/')}/status"
    deadline = monotonic() + readiness_timeout_seconds

    try:
        timeout = _remaining_timeout(deadline, request_timeout, monotonic)
        response, health_payload = _get_json_object(client, health_url, timeout)
        report(
            f"[pre-flight] GET {health_url}: OK "
            f"(HTTP {response.status_code}, healthy={health_payload.get('healthy')!r})"
        )
    except (httpx.HTTPError, ValueError, PreflightError) as exc:
        observed = f"{type(exc).__name__}: {exc}"
        report(f"[pre-flight] GET {health_url}: FAILED ({observed})")
        raise PreflightError(
            _health_failure_message(exc, health_url, base_url, observed)
        ) from exc

    last_observed = "no status response received"
    while monotonic() < deadline:
        try:
            timeout = _remaining_timeout(deadline, request_timeout, monotonic)
            response, payload = _get_json_object(client, status_url, timeout)
            last_observed = _state_description(payload)
            if payload.get("ready") is True:
                report(
                    f"[pre-flight] GET {status_url}: READY "
                    f"(HTTP {response.status_code}, {last_observed})"
                )
                return
            report(
                f"[pre-flight] GET {status_url}: WAITING "
                f"(HTTP {response.status_code}, {last_observed})"
            )
        except (httpx.HTTPError, ValueError, PreflightError) as exc:
            last_observed = f"{type(exc).__name__}: {exc}"
            report(f"[pre-flight] GET {status_url}: WAITING ({last_observed})")

        remaining = deadline - monotonic()
        if remaining > 0:
            sleep(min(poll_interval, remaining))

    raise PreflightError(
        _not_ready_message(
            base_url, status_url, readiness_timeout_seconds, last_observed
        )
    )


def _print_error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr, flush=True)


def run_preflight_or_exit(
    base_url: str,
    readiness_timeout_seconds: float,
    poll_interval: float,
    request_timeout: float,
    *,
    client: httpx.Client,
    report: Callable[[str], None] = print,
    report_error: Callable[[str], None] = _print_error,
) -> None:
    """Run pre-flight and terminate pytest distinctly on infrastructure failure.

    The full explanation goes to *report_error*; pytest's own exit banner
    only gets a short pointer to it, so the actionable text is not squashed
    into a single ``!!! Exit`` line.
    """
    try:
        wait_for_vippet_ready(
            base_url,
            readiness_timeout_seconds,
            poll_interval,
            request_timeout,
            client=client,
            report=report,
        )
    except PreflightError as exc:
        report_error(str(exc))
        pytest.exit(FATAL_PREFLIGHT_EXIT_REASON, returncode=FATAL_PREFLIGHT_EXIT_CODE)


def describe_discovery_error(exc: BaseException, base_url: str) -> str:
    """Explain a failed inventory read that happened *after* readiness passed."""
    return (
        "ViPPET reported ready, but reading its inventory (GET /pipelines, "
        f"/devices, /models) from {base_url} failed: {type(exc).__name__}: "
        f"{exc}. Without it no benchmark cases can be built. To fix: check the "
        "ViPPET logs (for example 'docker compose logs vippet') for errors on "
        "those endpoints, then rerun."
    )


def format_discovered_hardware(
    devices: Iterable[Mapping[str, Any]], vippet_version: str
) -> list[str]:
    """One line for the ViPPET version, then one per CPU/GPU/NPU family."""
    devices = list(devices)
    lines = [f"ViPPET version: {vippet_version}"]
    for family in sorted(SUPPORTED_DEVICE_FAMILIES):
        names = [
            str(device.get("full_device_name") or device.get("device_name") or "?")
            for device in devices
            if str(device.get("device_family") or "").upper() == family
        ]
        if names:
            lines.append(f"{family}: {', '.join(dict.fromkeys(names))}")
    if len(lines) == 1:
        lines.append(
            "No CPU, GPU or NPU device was discovered, so no benchmark case "
            "can run. To fix: see the GET /devices line above, and check that "
            "the ViPPET container has access to the host devices."
        )
    return lines


def fetch_discovered_devices(
    base_url: str,
    request_timeout: float,
    *,
    client: httpx.Client,
    report: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Fetch the ``/devices`` discovery payload for later hardware reporting.

    Called once at pre-flight time (after readiness is confirmed) so that the
    discovered hardware is captured independent of any individual test
    outcome -- a run where every case fails or is skipped still has this
    snapshot available for the report.

    Best-effort: any failure is logged via *report* and degrades to an empty
    list rather than raising, so a transient discovery error does not abort
    the performance run; the eventual report simply omits the hardware block.
    """
    devices_url = f"{base_url.rstrip('/')}/devices"
    try:
        response = client.get(devices_url, timeout=request_timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"expected a list, got {type(payload).__name__}")
        report(f"[pre-flight] GET {devices_url}: OK ({len(payload)} device(s))")
        return payload
    except (httpx.HTTPError, ValueError) as exc:
        report(
            f"[pre-flight] GET {devices_url}: FAILED ({type(exc).__name__}: {exc}). "
            "The report will have no hardware section. To fix: check the "
            "ViPPET logs for errors on GET /devices."
        )
        return []


def fetch_capabilities(
    capabilities_url: str,
    request_timeout: float,
    *,
    client: httpx.Client,
    report: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Fetch the metrics-manager ``/api/v1/capabilities`` snapshot.

    Best-effort, like ``fetch_discovered_devices``: any failure is logged via
    *report* and degrades to an empty dict, so a missing/unreachable
    metrics-manager does not abort the performance run; the report simply
    shows "Unknown" for the fields it would have supplied.
    """
    try:
        _, payload = _get_json_object(client, capabilities_url, request_timeout)
        report(f"[pre-flight] GET {capabilities_url}: OK")
        return payload
    except (httpx.HTTPError, ValueError) as exc:
        report(
            f"[pre-flight] GET {capabilities_url}: FAILED ({type(exc).__name__}: {exc}). "
            "The report will show CPU/GPU model and platform details as "
            "'Unknown'. To fix: make sure metrics-manager is running, or point "
            "--capabilities-url / VIPPET_CAPABILITIES_URL at it (by default "
            "the ViPPET host on port 9090)."
        )
        return {}


def _has_known_revision(value: Any) -> bool:
    """Return True unless *revision* is empty/missing or the literal "unknown".

    ``GET /status`` reports ``revision`` as the literal string ``"unknown"``
    (not ``null``) when ``VIPPET_REVISION`` wasn't set at build time (see
    ``app_version.py``), so a plain truthiness check isn't enough to detect
    an unknown revision.
    """
    return bool(value) and str(value).strip().lower() != "unknown"


def fetch_vippet_version(
    base_url: str,
    request_timeout: float,
    *,
    client: httpx.Client,
    report: Callable[[str], None] = print,
) -> str:
    """Fetch the ViPPET release/build version (and revision) from ``GET /status``.

    Best-effort: any failure is logged via *report* and degrades to
    ``"Unknown"`` rather than raising.
    """
    status_url = f"{base_url.rstrip('/')}/status"
    try:
        _, payload = _get_json_object(client, status_url, request_timeout)
        version = payload.get("version")
        if not version:
            raise ValueError("missing 'version' field")
        revision = payload.get("revision")
        display = (
            f"{version} ({revision})" if _has_known_revision(revision) else str(version)
        )
        report(
            f"[pre-flight] GET {status_url}: OK "
            f"(version={version!r}, revision={revision!r})"
        )
        return display
    except (httpx.HTTPError, ValueError) as exc:
        report(
            f"[pre-flight] GET {status_url}: FAILED ({type(exc).__name__}: {exc}). "
            "The report will show the ViPPET version as 'Unknown'. To fix: "
            "check that GET /status returns a 'version' field (ViPPET logs)."
        )
        return "Unknown"
