# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tool predictor: Protocol + OpenAI-compatible HTTP impl.

Pure HTTP wrapper. HTTP / parse failures raise PredictorError; empty-but-valid
responses return `(empty_candidates, raw_meta)` so the caller can distinguish
backend failure from "no relevant tools predicted".
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import requests

from ..core.exceptions import PredictorError
from ..core.health import HealthStatus


@dataclass(frozen=True)
class ToolCandidate:
    """One predicted tool. `name` is normalised (`.strip().lower()`),
    `score` is an int in [1, 5]."""

    name: str
    score: int


@runtime_checkable
class ToolPredictor(Protocol):
    """Predictor contract — for HTTPToolPredictor and test fakes."""

    name: str

    def predict(
        self,
        task: str,
        *,
        system_prompt: str,
    ) -> tuple[list[ToolCandidate], dict]: ...

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus: ...


# Tolerant tri-stage parser. Small predictor models often disobey "JSON only"
# — they wrap output in markdown fences, use single quotes, or prepend prose.
_JSON_BLOCK_RE: re.Pattern[str] = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_from_response(text: str) -> dict | None:
    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    for attempt in (text, text.replace("'", '"')):
        try:
            obj = json.loads(attempt)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            obj = json.loads(match.group())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return None


class HTTPToolPredictor:
    """OpenAI-compatible /v1/chat/completions client (vLLM / local LLM)."""

    name: str = "http_tool_predictor"

    def __init__(
        self,
        *,
        url: str,
        model: str,
        timeout: int = 120,
        health_endpoint: str | None = None,
    ) -> None:
        self._url = url
        self._model = model
        self._timeout = timeout
        if health_endpoint is None:
            # `.../v1/chat/completions` → `.../v1/models`; otherwise append.
            if url.endswith("/v1/chat/completions"):
                health_endpoint = url[: -len("/chat/completions")] + "/models"
            else:
                health_endpoint = url.rstrip("/") + "/v1/models"
        self._health_endpoint = health_endpoint

    @property
    def component(self) -> str:
        return f"predictor@{self._url}"

    def predict(
        self,
        task: str,
        *,
        system_prompt: str,
    ) -> tuple[list[ToolCandidate], dict]:
        """POST + parse → scored candidates. Empty-but-valid → empty list."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Task:\n{task}\n\nJSON:"},
            ],
            "temperature": 0.05,
            "max_tokens": 256,
            "stop": ["}"],
            "chat_template_kwargs": {"enable_thinking": False},
        }

        start = time.perf_counter()
        try:
            resp = requests.post(self._url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise PredictorError(
                f"HTTP request failed: {e}", component=self.component, cause=e,
            ) from e

        try:
            data = resp.json()
        except ValueError as e:
            raise PredictorError(
                f"Invalid JSON response: {e}", component=self.component, cause=e,
            ) from e

        try:
            predict_content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise PredictorError(
                f"Response missing choices[0].message.content: {e}",
                component=self.component,
                cause=e,
            ) from e

        if not isinstance(predict_content, str):
            raise PredictorError(
                "Response content is not a string",
                component=self.component,
            )

        predict_content = predict_content.strip()
        # `stop=["}"]` truncates the closing brace; restore for parsing.
        if predict_content.startswith("{") and not predict_content.endswith("}"):
            predict_content += "}"

        predict_dict = _extract_json_from_response(predict_content)
        if predict_dict is None:
            raise PredictorError(
                "Failed to parse JSON from predictor response",
                component=self.component,
            )

        candidates: list[ToolCandidate] = []
        for tool_name, score in predict_dict.items():
            if not isinstance(tool_name, str):
                continue
            try:
                score_int = int(score)
            except (ValueError, TypeError):
                continue
            if not (1 <= score_int <= 5):
                continue
            normalized = tool_name.strip().lower()
            if not normalized:
                continue
            candidates.append(ToolCandidate(name=normalized, score=score_int))

        # Deterministic order: descending score, then ascending name.
        candidates.sort(key=lambda c: (-c.score, c.name))

        latency_ms = (time.perf_counter() - start) * 1000
        raw_meta = {
            "model": self._model,
            "latency_ms": latency_ms,
            "raw_response": predict_content[:500],
        }
        return candidates, raw_meta

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        component = self.component
        start = time.perf_counter()
        try:
            resp = requests.get(self._health_endpoint, timeout=timeout)
            resp.raise_for_status()
        except Exception as e:
            return HealthStatus.unhealthy(component, str(e))

        latency_ms = (time.perf_counter() - start) * 1000
        try:
            body = resp.json()
        except ValueError as e:
            return HealthStatus.degraded(
                component, f"non-JSON response: {e}", latency_ms=latency_ms,
            )

        # OpenAI /v1/models shape: {"data": [{"id": "...", ...}, ...]}
        ids: list[str] = []
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        mid = entry.get("id")
                        if isinstance(mid, str):
                            ids.append(mid)

        if not ids:
            return HealthStatus.degraded(
                component, "no models listed in response", latency_ms=latency_ms,
            )

        if self._model in ids:
            return HealthStatus.healthy(component, latency_ms=latency_ms, models=ids)
        return HealthStatus.degraded(
            component,
            f"target model {self._model!r} not in registry",
            latency_ms=latency_ms,
            models=ids,
        )
