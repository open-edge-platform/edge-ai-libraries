# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tool predictor: Protocol + OpenAI-compatible HTTP impl.

Pure HTTP wrapper. HTTP / parse failures raise PredictorError; empty-but-valid
responses return `(empty_candidates, raw_meta)` so the caller can distinguish
backend failure from "no relevant tools predicted".
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

import requests

from ..core.exceptions import PredictorError
from ..core.health import HealthStatus
from ..core.metrics import estimate_tokens

# Reserved token budget for [CLS]/[SEP]/pair separators plus a safety cushion for
# the cl100k estimate vs. the backend's own tokenizer. Only used when a reranker
# is given `max_input_tokens` (see RerankerToolPredictor).
_RERANK_SPECIAL_TOKEN_MARGIN = 16


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolCandidate:
    """One predicted tool. `name` is normalised (`.strip().lower()`),
    `score` is in [1, 5]. Generative predictors return integer ratings;
    rerankers preserve their continuous relevance through this range."""

    name: str
    score: float


@dataclass(frozen=True)
class ToolDefinition:
    """Structured candidate presented to a reranker."""

    name: str
    description: str = ""
    parameters: dict | None = None


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

# Last-resort salvage for truncated output. When `stop=["}"]` + `max_tokens`
# cut a multi-line `{"name": score, ...}` object mid-key, no `}` is ever emitted
# and json.loads fails on the whole thing. This recovers every complete
# `"name": <1-5>` pair and drops the severed tail, so truncation degrades to
# losing a trailing tool or two instead of failing the whole prediction.
_PAIR_RE: re.Pattern[str] = re.compile(r'"([^"]+)"\s*:\s*([1-5])\b')


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

    # Salvage complete `"name": <score>` pairs from truncated/garbled output.
    pairs = _PAIR_RE.findall(text)
    if pairs:
        return {name: int(score) for name, score in pairs}
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
        enforce_json_schema: bool = False,
        max_output_tokens: int = 256,
        health_endpoint: str | None = None,
    ) -> None:
        self._url = url
        self._model = model
        self._timeout = timeout
        self._enforce_json_schema = enforce_json_schema
        self._max_output_tokens = max_output_tokens
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
        tool_names: list[str] | None = None,
    ) -> tuple[list[ToolCandidate], dict]:
        """POST + parse → scored candidates. Empty-but-valid → empty list."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Task:\n{task}\n\nJSON:"},
            ],
            "temperature": 0.05,
            "max_tokens": self._max_output_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self._enforce_json_schema:
            score_schema = {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
            }
            schema: dict = {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": score_schema,
            }
            if tool_names:
                names = list(dict.fromkeys(tool_names))
                schema["properties"] = {name: score_schema for name in names}
                schema["additionalProperties"] = False
                # Guided decoding emits keys in declaration order; with optional
                # keys the model can only skip forward, so early tools
                # (read/edit/...) are lost once passed. Requiring every key
                # turns it into one rating per tool and leaves selection to
                # score_threshold.
                # TODO: every request now spells out all tool names, so latency
                # grows with the tool count. Switch to a fixed-length score
                # array (`{"scores": [5, 3, ...]}` in `names` order) so the model
                # emits only the scores, then map positions back to names.
                schema["required"] = names
                # ~10 tokens per pretty-printed `"name": n,` line; a truncated
                # object would drop the tail tools.
                payload["max_tokens"] = max(
                    self._max_output_tokens, 12 * len(names) + 32,
                )
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "tool_scores",
                    "schema": schema,
                },
            }
        else:
            payload["stop"] = ["}"]

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
            choice = data["choices"][0]
            predict_content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
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
            "finish_reason": finish_reason,
            "raw_response": predict_content[:2000],
            "raw_response_length": len(predict_content),
            "raw_tool_count": len(predict_dict),
            "parsed_candidate_count": len(candidates),
        }
        return candidates, raw_meta

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        component = self.component
        start = time.perf_counter()
        try:
            resp = requests.get(self._health_endpoint, timeout=timeout)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Predictor health check failed for %s: %s", component, type(e).__name__)
            return HealthStatus.unhealthy(component, "predictor unavailable")

        latency_ms = (time.perf_counter() - start) * 1000
        try:
            body = resp.json()
        except ValueError as e:
            logger.warning("Predictor returned invalid health response for %s: %s", component, type(e).__name__)
            return HealthStatus.degraded(
                component, "predictor returned invalid response", latency_ms=latency_ms,
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


class RerankerToolPredictor:
    """Batch tool relevance predictor using a Jina/Cohere-style `/rerank` API."""

    name: str = "reranker_tool_predictor"
    requires_tool_definitions: bool = True

    def __init__(
        self,
        *,
        url: str,
        model: str,
        timeout: int = 120,
        score_mode: Literal["probability", "logit"] = "probability",
        instruction: str = (
            "Determine whether this tool may be needed for the current agent "
            "task or its next step. Favor recall: include direct tools, likely "
            "dependencies, and reasonable fallbacks."
        ),
        max_input_tokens: int | None = None,
        health_endpoint: str | None = None,
    ) -> None:
        self._url = url
        self._model = model
        self._timeout = timeout
        self._score_mode = score_mode
        self._instruction = instruction
        # Context ceiling of the reranker backend. When None (default) the query
        # is sent verbatim and no shrink-retry runs — non-capped rerankers (e.g.
        # Qwen3-Reranker, 32k) are byte-identical. Set it ONLY for models whose
        # window is small enough that the composed query can overflow (e.g.
        # bge-reranker-v2-m3, absolute-position XLM-RoBERTa hard-capped at 8192).
        self._max_input_tokens = (
            int(max_input_tokens) if max_input_tokens else None
        )
        if health_endpoint is None:
            base = url.rstrip("/")
            for suffix in ("/v1/rerank", "/rerank"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            health_endpoint = base + "/v1/models"
        self._health_endpoint = health_endpoint

    @property
    def component(self) -> str:
        return f"reranker@{self._url}"

    def _fit_query(self, query: str, documents: list[str]) -> str:
        """Trim the tail of `query` so the longest (query, document) pair fits the
        backend's context window. Keeps the head (Instruction + Task); only the
        trailing Agent-context is dropped. No-op when `max_input_tokens` is None,
        so non-capped rerankers are unaffected. `estimate_tokens` is cl100k; a
        sentencepiece backend may count more, so we shrink until safely under and
        `_post_rerank` retries if the backend still rejects the pair."""
        if not self._max_input_tokens:
            return query
        reserve = max((estimate_tokens(doc) for doc in documents), default=0)
        budget = self._max_input_tokens - reserve - _RERANK_SPECIAL_TOKEN_MARGIN
        if budget < 1:
            budget = max(1, self._max_input_tokens // 2)
        if estimate_tokens(query) <= budget:
            return query
        est = estimate_tokens(query) or 1
        trimmed = query[: max(1, int(len(query) * budget / est))]
        while trimmed and estimate_tokens(trimmed) > budget:
            trimmed = trimmed[: max(1, int(len(trimmed) * 0.9))]
        return trimmed

    def _post_rerank(self, query: str, documents: list[str]) -> requests.Response:
        """POST to the rerank endpoint. When `max_input_tokens` is set and the
        backend still rejects a pair for length (estimate undercount), shrink the
        query tail and retry, bounded. When it is None the request is sent once,
        unchanged — guaranteeing this path is inert for non-capped rerankers."""
        current = query
        resp: requests.Response | None = None
        for _ in range(6):
            resp = requests.post(
                self._url,
                json={
                    "model": self._model,
                    "query": current,
                    "documents": documents,
                    "top_n": len(documents),
                },
                timeout=self._timeout,
            )
            if (
                self._max_input_tokens
                and resp.status_code == 400
                and len(current) > 200
                and "context length" in resp.text.lower()
            ):
                current = current[: int(len(current) * 0.7)]
                continue
            return resp
        return resp  # type: ignore[return-value]

    @staticmethod
    def _render_document(tool: ToolDefinition) -> str:
        parts = [f"Tool name: {tool.name}"]
        if tool.description:
            parts.append(f"Description: {tool.description}")
        if tool.parameters:
            parts.append(
                "Parameters: "
                + json.dumps(tool.parameters, ensure_ascii=False, separators=(",", ":"))
            )
        return "\n".join(parts)

    def _to_probability(self, score: float) -> float:
        if self._score_mode == "logit":
            if score >= 0:
                z = math.exp(-score)
                return 1.0 / (1.0 + z)
            z = math.exp(score)
            return z / (1.0 + z)
        if not 0.0 <= score <= 1.0:
            raise PredictorError(
                f"Reranker probability outside [0, 1]: {score!r}",
                component=self.component,
            )
        return score

    def predict(
        self,
        task: str,
        *,
        system_prompt: str,
        tool_definitions: list[ToolDefinition] | None = None,
    ) -> tuple[list[ToolCandidate], dict]:
        """Score every supplied tool in one request and preserve all scores."""
        if not tool_definitions:
            return [], {"model": self._model, "latency_ms": 0.0, "scores": {}}

        query_parts = [f"Task:\n{task}"]
        instruction = self._instruction.strip()
        if instruction:
            query_parts.insert(0, f"Instruction:\n{instruction}")
        context = system_prompt.strip()
        if context:
            query_parts.append(f"Agent context:\n{context}")
        query = "\n\n".join(query_parts)
        documents = [self._render_document(tool) for tool in tool_definitions]
        query = self._fit_query(query, documents)

        start = time.perf_counter()
        try:
            resp = self._post_rerank(query, documents)
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

        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise PredictorError(
                "Reranker response missing results array",
                component=self.component,
            )

        probabilities: dict[int, float] = {}
        for result in results:
            if not isinstance(result, dict):
                continue
            index = result.get("index")
            raw_score = result.get("relevance_score")
            if (
                not isinstance(index, int)
                or isinstance(raw_score, bool)
                or not isinstance(raw_score, (int, float))
                or not math.isfinite(float(raw_score))
                or index in probabilities
            ):
                continue
            if 0 <= index < len(tool_definitions):
                probabilities[index] = self._to_probability(float(raw_score))

        expected = set(range(len(tool_definitions)))
        if set(probabilities) != expected:
            missing = sorted(expected - set(probabilities))
            raise PredictorError(
                f"Reranker returned incomplete scores; missing indices: {missing}",
                component=self.component,
            )

        candidates = [
            ToolCandidate(
                name=tool_definitions[index].name.strip().lower(),
                score=1.0 + 4.0 * probabilities[index],
            )
            for index in range(len(tool_definitions))
            if tool_definitions[index].name.strip()
        ]
        candidates.sort(key=lambda candidate: (-candidate.score, candidate.name))
        latency_ms = (time.perf_counter() - start) * 1000
        return candidates, {
            "model": self._model,
            "latency_ms": latency_ms,
            "score_mode": self._score_mode,
            "scores": {
                tool_definitions[index].name: probabilities[index]
                for index in range(len(tool_definitions))
            },
        }

    def health_check(self, *, timeout: float = 5.0) -> HealthStatus:
        component = self.component
        start = time.perf_counter()
        try:
            resp = requests.get(self._health_endpoint, timeout=timeout)
            resp.raise_for_status()
            body = resp.json()
        except Exception:
            return HealthStatus.unhealthy(component, "reranker unavailable")

        latency_ms = (time.perf_counter() - start) * 1000
        entries = body.get("data") if isinstance(body, dict) else None
        ids = [
            entry["id"] for entry in entries or []
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        ]
        if self._model in ids:
            return HealthStatus.healthy(component, latency_ms=latency_ms, models=ids)
        return HealthStatus.degraded(
            component,
            f"target model {self._model!r} not in registry",
            latency_ms=latency_ms,
            models=ids,
        )
