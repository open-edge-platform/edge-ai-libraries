"""Thin async HTTP client for a single ViPPET instance.

Every call is defensive: a ViPPET instance may be offline, mid-initialisation or
running an older API revision, and one bad instance must never break the portal.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger("portal.vippet")

API_PREFIX = "/api/v1"


class VippetUnavailable(Exception):
    """Raised when an instance cannot serve a request."""


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message")
        if detail:
            return str(detail)
    return f"HTTP {response.status_code}"


class VippetClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    async def _get(self, path: str) -> Any:
        url = f"{self.base_url}{API_PREFIX}{path}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.debug("GET %s failed: %s", url, exc)
            raise VippetUnavailable(str(exc)) from exc

    async def _post(self, path: str, json: Any | None = None) -> Any:
        url = f"{self.base_url}{API_PREFIX}{path}"
        try:
            response = await self._client.post(url, json=json)
        except httpx.HTTPError as exc:
            logger.debug("POST %s failed: %s", url, exc)
            raise VippetUnavailable(str(exc)) from exc
        if response.is_error:
            raise VippetUnavailable(_error_detail(response))
        try:
            return response.json()
        except ValueError as exc:
            raise VippetUnavailable(str(exc)) from exc

    async def status(self) -> dict[str, Any]:
        payload = await self._get("/status")
        return payload if isinstance(payload, dict) else {}

    async def devices(self) -> list[dict[str, Any]]:
        payload = await self._get("/devices")
        return payload if isinstance(payload, list) else []

    async def benchmark_suites(self) -> list[dict[str, Any]]:
        payload = await self._get("/benchmarks")
        return payload if isinstance(payload, list) else []

    async def start_benchmark_suite(self, suite_slug: str) -> str:
        """Launch a suite and return the id of the created job."""
        payload = await self._post(f"/benchmarks/{suite_slug}/run")
        job_id = payload.get("job_id") if isinstance(payload, dict) else None
        if not job_id:
            raise VippetUnavailable("instance did not return a job id")
        return str(job_id)

    async def benchmark_job_statuses(self) -> list[dict[str, Any]]:
        payload = await self._get("/jobs/tests/benchmark/status")
        return payload if isinstance(payload, list) else []

    async def benchmark_runs(self) -> list[dict[str, Any]]:
        payload = await self._get("/benchmarks/runs")
        return payload if isinstance(payload, list) else []

    async def benchmark_run_details(self, suite_slug: str, run_id: int) -> dict[str, Any]:
        payload = await self._get(f"/benchmarks/{suite_slug}/run/{run_id}")
        return payload if isinstance(payload, dict) else {}

    async def job_statuses(self, kind: str) -> list[dict[str, Any]]:
        payload = await self._get(f"/jobs/tests/{kind}/status")
        return payload if isinstance(payload, list) else []

    async def pipelines(self) -> list[dict[str, Any]]:
        payload = await self._get("/pipelines")
        return payload if isinstance(payload, list) else []

    async def start_test(self, kind: str, spec: dict[str, Any]) -> str:
        """Launch a performance or density test and return the new job id."""
        payload = await self._post(f"/tests/{kind}", json=spec)
        job_id = payload.get("job_id") if isinstance(payload, dict) else None
        if not job_id:
            raise VippetUnavailable("instance did not return a job id")
        return str(job_id)

    async def job_summary(self, kind: str, job_id: str) -> dict[str, Any]:
        payload = await self._get(f"/jobs/tests/{kind}/{job_id}")
        return payload if isinstance(payload, dict) else {}


def make_http_client() -> httpx.AsyncClient:
    # trust_env=False: corporate HTTP(S)_PROXY settings must not hijack calls to
    # testbed machines on the local network.
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout),
        trust_env=False,
        follow_redirects=True,
    )
