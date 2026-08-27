# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Database-agnostic gateway to the downstream storage HTTP API."""

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from .runtime_config import RuntimeSettings, load_runtime_settings

log = logging.getLogger(__name__)

_NO_PROXY = {"http": None, "https": None}  # bypass system proxy for internal Docker calls
_RETRYABLE_STATUS_CODES = {429, *range(500, 600)}


class StorageError(RuntimeError):
    """Base error for downstream storage failures."""


class StorageConnectionError(StorageError):
    """Raised when the downstream storage service cannot be reached."""


class StorageHTTPError(StorageError):
    """Raised when the downstream storage service rejects a request."""

    def __init__(self, method: str, path: str, status_code: int):
        self.status_code = status_code
        super().__init__(
            f"Storage request {method} {path} failed with HTTP {status_code}"
        )


class StorageContractError(StorageError):
    """Raised when the downstream service violates the storage contract."""


@dataclass(frozen=True)
class StorageClient:
    """HTTP implementation of the required downstream storage contract."""

    base_url: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    read_max_attempts: int
    retry_backoff_seconds: float

    @classmethod
    def from_settings(cls, settings: RuntimeSettings) -> "StorageClient":
        return cls(
            base_url=settings.storage_service_url,
            connect_timeout_seconds=settings.storage_connect_timeout_seconds,
            read_timeout_seconds=settings.storage_read_timeout_seconds,
            read_max_attempts=settings.storage_read_max_attempts,
            retry_backoff_seconds=settings.storage_retry_backoff_seconds,
        )

    @property
    def timeout(self) -> tuple[float, float]:
        return self.connect_timeout_seconds, self.read_timeout_seconds

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected_type: type,
        params: dict[str, Any] | None = None,
        payload: dict | None = None,
    ) -> Any:
        attempts = self.read_max_attempts if method == "GET" else 1
        response = None
        for attempt in range(1, attempts + 1):
            try:
                request = requests.get if method == "GET" else requests.post
                kwargs: dict[str, Any] = {
                    "timeout": self.timeout,
                    "proxies": _NO_PROXY,
                }
                if params is not None:
                    kwargs["params"] = params
                if payload is not None:
                    kwargs["json"] = payload
                response = request(f"{self.base_url}{path}", **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt < attempts:
                    self._backoff(attempt, method, path)
                    continue
                raise StorageConnectionError(
                    f"Storage request {method} {path} failed after {attempt} attempt(s)"
                ) from exc

            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < attempts:
                self._backoff(attempt, method, path)
                continue
            if not 200 <= response.status_code < 300:
                raise StorageHTTPError(method, path, response.status_code)
            break

        try:
            data = response.json()
        except (requests.JSONDecodeError, ValueError) as exc:
            raise StorageContractError(
                f"Storage response {method} {path} is not valid JSON"
            ) from exc
        if not isinstance(data, expected_type):
            expected_name = "array" if expected_type is list else "object"
            raise StorageContractError(
                f"Storage response {method} {path} must be a JSON {expected_name}"
            )
        return data

    def _backoff(self, attempt: int, method: str, path: str) -> None:
        delay = self.retry_backoff_seconds * (2 ** (attempt - 1))
        log.warning(
            "Retrying storage request %s %s after attempt %d in %.2fs",
            method,
            path,
            attempt,
            delay,
        )
        if delay:
            time.sleep(delay)

    def get_detections(
        self,
        label: str | None = None,
        min_confidence: float | None = None,
        limit: int | None = 500,
        min_id: int | None = None,
        max_id: int | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if label:
            params["label"] = label
        if min_confidence is not None:
            params["min_confidence"] = min_confidence
        if limit is not None:
            params["limit"] = limit
        if min_id is not None:
            params["min_id"] = min_id
        if max_id is not None:
            params["max_id"] = max_id
        return self._request(
            "GET", "/detections", expected_type=list, params=params
        )

    def get_summary(
        self, min_id: int | None = None, max_id: int | None = None
    ) -> dict:
        params = {}
        if min_id is not None:
            params["min_id"] = min_id
        if max_id is not None:
            params["max_id"] = max_id
        return self._request(
            "GET", "/detections/summary", expected_type=dict, params=params
        )


def _client() -> StorageClient:
    return StorageClient.from_settings(load_runtime_settings())


def get_detections(
    label: str | None = None,
    min_confidence: float | None = None,
    limit: int | None = 500,
    min_id: int | None = None,
    max_id: int | None = None,
) -> list[dict]:
    return _client().get_detections(label, min_confidence, limit, min_id, max_id)


def get_summary(
    min_id: int | None = None, max_id: int | None = None
) -> dict:
    return _client().get_summary(min_id, max_id)
