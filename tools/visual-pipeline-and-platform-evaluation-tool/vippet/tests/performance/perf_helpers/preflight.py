# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ViPPET reachability and readiness checks for performance tests."""

import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

FATAL_PREFLIGHT_EXIT_CODE = 2


class PreflightError(RuntimeError):
    """Raised when ViPPET cannot become ready for performance discovery."""


def _remaining_timeout(
    deadline: float,
    request_timeout: float,
    monotonic: Callable[[], float],
) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise PreflightError("readiness timeout expired")
    return min(request_timeout, remaining)


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
    client: httpx.Client | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    report: Callable[[str], None] = print,
) -> None:
    """Check ViPPET health and wait for its status endpoint to report ready."""
    health_url = f"{base_url.rstrip('/')}/health"
    status_url = f"{base_url.rstrip('/')}/status"
    deadline = monotonic() + readiness_timeout_seconds
    remedy = "Start ViPPET and wait for its initialization."
    owned_client = client is None
    active_client = client or httpx.Client(headers={"Accept": "application/json"})

    try:
        try:
            timeout = _remaining_timeout(deadline, request_timeout, monotonic)
            response, health_payload = _get_json_object(
                active_client, health_url, timeout
            )
            report(
                f"[pre-flight] GET {health_url}: OK "
                f"(HTTP {response.status_code}, healthy={health_payload.get('healthy')!r})"
            )
        except (httpx.HTTPError, ValueError, PreflightError) as exc:
            observed = f"{type(exc).__name__}: {exc}"
            report(f"[pre-flight] GET {health_url}: FAILED ({observed})")
            raise PreflightError(
                f"ViPPET pre-flight failed for {health_url}; observed {observed}. "
                f"Remedy: {remedy}"
            ) from exc

        last_observed = "no status response received"
        while monotonic() < deadline:
            try:
                timeout = _remaining_timeout(deadline, request_timeout, monotonic)
                response, payload = _get_json_object(active_client, status_url, timeout)
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
            f"ViPPET pre-flight timed out after {readiness_timeout_seconds:g}s "
            f"waiting for {status_url}; last observed {last_observed}. "
            f"Remedy: {remedy}"
        )
    finally:
        if owned_client:
            active_client.close()


def run_preflight_or_exit(
    base_url: str,
    readiness_timeout_seconds: float,
    poll_interval: float,
    request_timeout: float,
) -> None:
    """Run pre-flight and terminate pytest distinctly on infrastructure failure."""
    try:
        wait_for_vippet_ready(
            base_url,
            readiness_timeout_seconds,
            poll_interval,
            request_timeout,
        )
    except PreflightError as exc:
        pytest.exit(str(exc), returncode=FATAL_PREFLIGHT_EXIT_CODE)
