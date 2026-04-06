"""HTTP client for the selected Video Search and Summarization backend endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any

import httpx

from .config import Settings


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VSSServiceError(Exception):
    """A transport-level error while calling the VSS backend."""

    status_code: int
    detail: str


@dataclass(slots=True)
class VSSResponse:
    """Normalized VSS backend response used by tools and resources."""

    endpoint: str
    method: str
    status_code: int
    ok: bool
    content_type: str | None
    headers: dict[str, str]
    content_size_bytes: int
    data: Any = None
    text: str | None = None
    binary_body: bytes | None = None
    note: str | None = None


class VSSApiClient:
    """Async HTTP client for the VSS backend."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        """Create the shared outbound client."""

        self._client = httpx.AsyncClient(
            base_url=self._settings.vss_base_url,
            follow_redirects=False,
            timeout=self._settings.request_timeout_seconds,
            headers=self._build_default_headers(),
        )

    async def close(self) -> None:
        """Close the shared outbound client."""

        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        *,
        method: str,
        path: str,
        query_params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        include_binary_content: bool = False,
    ) -> VSSResponse:
        """Call the VSS backend and normalize the response body."""

        client = self._require_client()
        started_at = perf_counter()

        try:
            response = await client.request(
                method=method,
                url=path,
                params=query_params,
                json=json_body,
                data=data,
                files=files,
            )
        except httpx.TimeoutException as exc:
            logger.exception("Timed out while calling VSS %s %s", method, path)
            raise VSSServiceError(
                status_code=504,
                detail="Timed out while waiting for the VSS backend.",
            ) from exc
        except httpx.RequestError as exc:
            logger.exception("Failed to call VSS %s %s", method, path)
            raise VSSServiceError(
                status_code=502,
                detail="Unable to reach the VSS backend.",
            ) from exc

        duration_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "VSS %s %s -> %s (%.2f ms)",
            method,
            path,
            response.status_code,
            duration_ms,
        )
        return self._build_response(
            response,
            method=method,
            path=path,
            include_binary_content=include_binary_content,
        )

    def _build_default_headers(self) -> dict[str, str]:
        """Build headers applied to every outbound VSS request."""

        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "vss-mcp/0.1.0",
        }
        if self._settings.vss_api_token:
            headers["Authorization"] = (
                f"{self._settings.vss_auth_scheme} {self._settings.vss_api_token}"
            )
        return headers

    def _build_response(
        self,
        response: httpx.Response,
        *,
        method: str,
        path: str,
        include_binary_content: bool,
    ) -> VSSResponse:
        """Normalize an HTTP response for tool and resource formatting."""

        content_type = response.headers.get("content-type")
        content_type_normalized = content_type.lower() if content_type else ""
        note: str | None = None
        data: Any = None
        text: str | None = None
        binary_body: bytes | None = None

        if "application/json" in content_type_normalized:
            try:
                data = response.json()
            except ValueError:
                text = response.text
                note = "The backend advertised JSON but returned an invalid JSON payload."
        elif content_type_normalized.startswith("text/") or any(
            marker in content_type_normalized for marker in ("xml", "yaml", "csv")
        ):
            text = response.text
        elif include_binary_content:
            binary_body = response.content
        else:
            note = (
                "Binary content was omitted from this result. Re-run the tool with "
                "include_binary_content=true to receive a base64 payload."
            )

        return VSSResponse(
            endpoint=path,
            method=method,
            status_code=response.status_code,
            ok=response.is_success,
            content_type=content_type,
            headers=dict(response.headers),
            content_size_bytes=len(response.content),
            data=data,
            text=text,
            binary_body=binary_body,
            note=note,
        )

    def _require_client(self) -> httpx.AsyncClient:
        """Return the initialized client or fail fast."""

        if self._client is None:  # pragma: no cover - guarded by application startup
            raise RuntimeError("The VSS API client is not initialized.")
        return self._client
