"""HTTP client for the selected spec-driven REST proxy target."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import logging
import re
from time import perf_counter
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .models import FileUpload


logger = logging.getLogger(__name__)
PATH_PARAMETER_PATTERN = re.compile(r"{([^{}]+)}")


@dataclass(slots=True)
class ProxyServiceError(Exception):
    """A transport-level error while calling the target REST API."""

    status_code: int
    detail: str


@dataclass(slots=True)
class ProxyResponse:
    """Normalized target API response used by tools and resources."""

    operation: str
    operation_id: str | None
    endpoint: str
    url: str
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


class ProxyApiClient:
    """Async HTTP client for the proxied REST API."""

    def __init__(self, settings: Settings, *, base_url: str) -> None:
        self._settings = settings
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        """Create the shared outbound client."""

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
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
        operation: str,
        operation_id: str | None,
        method: str,
        path_template: str,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
        form_data: dict[str, str] | None = None,
        files: dict[str, FileUpload] | None = None,
        text_body: str | None = None,
        binary_body_base64: str | None = None,
        include_binary_content: bool = False,
    ) -> ProxyResponse:
        """Call the target API and normalize the response body."""

        client = self._require_client()
        started_at = perf_counter()
        resolved_path = _resolve_path(path_template, path_params)
        request_headers = self._merge_headers(headers)
        body_kwargs = _build_body_kwargs(
            json_body=json_body,
            form_data=form_data,
            files=files,
            text_body=text_body,
            binary_body_base64=binary_body_base64,
        )

        try:
            response = await client.request(
                method=method,
                url=resolved_path,
                params=_normalize_scalar_mapping(query_params),
                headers=request_headers,
                **body_kwargs,
            )
        except httpx.TimeoutException as exc:
            logger.exception("Timed out while calling %s %s", method, resolved_path)
            raise ProxyServiceError(
                status_code=504,
                detail="Timed out while waiting for the target REST API.",
            ) from exc
        except httpx.RequestError as exc:
            logger.exception("Failed to call %s %s", method, resolved_path)
            raise ProxyServiceError(
                status_code=502,
                detail="Unable to reach the target REST API.",
            ) from exc

        duration_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "Target API %s %s -> %s (%.2f ms)",
            method,
            resolved_path,
            response.status_code,
            duration_ms,
        )
        return self._build_response(
            response,
            operation=operation,
            operation_id=operation_id,
            method=method,
            path=resolved_path,
            include_binary_content=include_binary_content,
        )

    def _build_default_headers(self) -> dict[str, str]:
        """Build headers applied to every outbound target API request."""

        headers = {
            "Accept": "*/*",
            "User-Agent": "app-proxy-mcp/0.2.0",
        }
        return headers

    def _build_response(
        self,
        response: httpx.Response,
        *,
        operation: str,
        operation_id: str | None,
        method: str,
        path: str,
        include_binary_content: bool,
    ) -> ProxyResponse:
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
                note = "The target API advertised JSON but returned an invalid JSON payload."
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

        return ProxyResponse(
            operation=operation,
            operation_id=operation_id,
            endpoint=path,
            url=str(response.request.url),
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

    def _merge_headers(self, headers: dict[str, str] | None) -> dict[str, str] | None:
        """Return per-request header overrides (httpx client already carries defaults)."""

        return headers or None

    def _require_client(self) -> httpx.AsyncClient:
        """Return the initialized client or fail fast."""

        if self._client is None:  # pragma: no cover - guarded by application startup
            raise RuntimeError("The proxy API client is not initialized.")
        return self._client


def _resolve_path(path_template: str, path_params: dict[str, Any] | None) -> str:
    """Resolve an OpenAPI-style path template using supplied path params."""

    supplied_path_params = path_params or {}

    def replacer(match: re.Match[str]) -> str:
        parameter_name = match.group(1)
        if parameter_name not in supplied_path_params or supplied_path_params[parameter_name] is None:
            raise ProxyServiceError(
                status_code=400,
                detail=f"Missing required path parameter: {parameter_name}",
            )
        return quote(_serialize_scalar(supplied_path_params[parameter_name]), safe="")

    return PATH_PARAMETER_PATTERN.sub(replacer, path_template)


def _build_body_kwargs(
    *,
    json_body: dict[str, Any] | list[Any] | None,
    form_data: dict[str, str] | None,
    files: dict[str, FileUpload] | None,
    text_body: str | None,
    binary_body_base64: str | None,
) -> dict[str, Any]:
    """Normalize the body payload into httpx-compatible kwargs."""

    has_form_payload = bool(form_data) or bool(files)
    body_mode_count = sum(
        [
            json_body is not None,
            has_form_payload,
            text_body is not None,
            binary_body_base64 is not None,
        ]
    )
    if body_mode_count > 1:
        raise ProxyServiceError(
            status_code=400,
            detail=(
                "Provide only one request body shape at a time: json_body, form_data/files, "
                "text_body, or binary_body_base64."
            ),
        )

    if json_body is not None:
        return {"json": json_body}
    if text_body is not None:
        return {"content": text_body}
    if binary_body_base64 is not None:
        try:
            return {"content": base64.b64decode(binary_body_base64)}
        except ValueError as exc:
            raise ProxyServiceError(
                status_code=400,
                detail="binary_body_base64 must be valid base64.",
            ) from exc
    if has_form_payload:
        return {
            "data": form_data or None,
            "files": _normalize_files(files),
        }
    return {}


def _normalize_files(files: dict[str, FileUpload] | None) -> dict[str, tuple[str, bytes, str]] | None:
    """Convert file upload models to the tuple form expected by httpx."""

    if not files:
        return None

    normalized: dict[str, tuple[str, bytes, str]] = {}
    for field_name, upload in files.items():
        try:
            content = base64.b64decode(upload.content_base64)
        except ValueError as exc:
            raise ProxyServiceError(
                status_code=400,
                detail=f"File field {field_name!r} contains invalid base64 content.",
            ) from exc
        normalized[field_name] = (upload.filename, content, upload.content_type)
    return normalized


def _normalize_scalar_mapping(values: dict[str, Any] | None) -> dict[str, str] | None:
    """Convert supported scalar values into strings for query/path/header use."""

    if not values:
        return None
    return {name: _serialize_scalar(value) for name, value in values.items() if value is not None}


def _serialize_scalar(value: Any) -> str:
    """Serialize a scalar value consistently for HTTP transport."""

    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
