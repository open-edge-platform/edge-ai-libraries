# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Generic VLM Client for OpenVINO Model Server.

Sends images + configurable prompts to a VLM endpoint and parses
structured JSON responses. Knows nothing about specific behaviors —
the prompt and response schema are fully driven by configuration.
"""

import asyncio
import base64
import io
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class VLMResult:
    """Result from VLM analysis."""

    raw_response: str
    parsed: Optional[dict[str, Any]] = None
    success: bool = False
    error: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None


class VLMClient:
    """
    Async client for OpenAI-compatible VLM endpoints (OVMS).

    Includes a circuit breaker that opens after consecutive failures,
    preventing request storms against a broken OVMS instance. The
    breaker auto-recovers by probing OVMS health after a cooldown.

    Usage:
        client = VLMClient(endpoint="http://ovms-vlm:8000", model_name="Qwen/...")
        result = await client.analyze(frames, prompt="Describe what you see.")
    """

    def __init__(
        self,
        endpoint: str = "http://ovms-vlm:8000",
        model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct",
        timeout: float = 60.0,
        max_tokens: int = 100,
        temperature: float = 0.1,
        max_image_size: int = 256,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_cooldown: float = 30.0,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_image_size = max_image_size

        # Persistent HTTP client — reuses TCP connections across requests
        self._http_client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            http2=True,
        )

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_opened_at = 0.0
        self._cb_threshold = circuit_breaker_threshold
        self._cb_cooldown = circuit_breaker_cooldown

    async def close(self) -> None:
        """Shut down the persistent HTTP client."""
        await self._http_client.aclose()

    def _encode_frame(self, frame: np.ndarray) -> str:
        """Resize and encode a frame as progressive JPEG."""
        h, w = frame.shape[:2]
        if max(h, w) > self.max_image_size:
            scale = self.max_image_size / max(h, w)
            frame = cv2.resize(
                frame,
                (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )

        # Convert BGR (OpenCV) → RGB (PIL) and encode as progressive JPEG
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80, optimize=True, progressive=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _build_messages(
        self,
        frames: list[np.ndarray],
        prompt: str,
    ) -> list[dict]:
        """Build OpenAI-compatible chat messages with images."""
        content = []

        # Text prompt first — VLM can start prefilling while images load
        content.append({"type": "text", "text": prompt})

        # Add images after text
        for frame in frames:
            b64 = self._encode_frame(frame)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )

        return [
            {"role": "system", "content": "You are a CCTV surveillance analyst. Respond with JSON only, no extra text."},
            {"role": "user", "content": content},
        ]

    async def _check_circuit_breaker(self) -> Optional[VLMResult]:
        """Check if circuit breaker is open. Returns error result if open, None if closed."""
        if not self._circuit_open:
            return None

        elapsed = time.perf_counter() - self._circuit_opened_at
        if elapsed < self._cb_cooldown:
            logger.debug(
                "Circuit breaker OPEN — skipping VLM request (%.0fs remaining)",
                self._cb_cooldown - elapsed,
            )
            return VLMResult(
                raw_response="",
                success=False,
                error=f"Circuit breaker open ({self._cb_cooldown - elapsed:.0f}s remaining)",
            )

        # Cooldown elapsed — try a health probe before closing circuit
        logger.info("Circuit breaker cooldown elapsed, probing VLM health...")
        try:
            r = await self._http_client.post(
                f"{self.endpoint}/v3/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                },
                timeout=10.0,
            )
            if r.status_code == 200:
                self._circuit_open = False
                self._consecutive_failures = 0
                logger.info("Circuit breaker CLOSED — VLM recovered")
                return None
            else:
                # Still broken, reset cooldown
                self._circuit_opened_at = time.perf_counter()
                logger.warning("VLM still unhealthy (HTTP %s), circuit stays open", r.status_code)
                return VLMResult(
                    raw_response="",
                    success=False,
                    error=f"VLM unhealthy after cooldown (HTTP {r.status_code})",
                )
        except Exception as e:
            self._circuit_opened_at = time.perf_counter()
            logger.warning("VLM health probe failed: %s, circuit stays open", e)
            return VLMResult(
                raw_response="",
                success=False,
                error=f"VLM health probe failed: {e}",
            )

    def _record_success(self):
        """Record a successful VLM call."""
        self._consecutive_failures = 0
        if self._circuit_open:
            self._circuit_open = False
            logger.info("Circuit breaker CLOSED after successful response")

    def _record_failure(self, error: str):
        """Record a failed VLM call and potentially open the circuit."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._cb_threshold and not self._circuit_open:
            self._circuit_open = True
            self._circuit_opened_at = time.perf_counter()
            logger.error(
                "Circuit breaker OPENED after %d consecutive failures (cooldown=%.0fs). Last error: %s",
                self._consecutive_failures,
                self._cb_cooldown,
                error,
            )

    async def analyze(
        self,
        frames: list[np.ndarray],
        prompt: str,
    ) -> VLMResult:
        """
        Send frames and prompt to VLM and return parsed result.

        Args:
            frames: List of BGR numpy arrays (images)
            prompt: The analysis prompt to send

        Returns:
            VLMResult with parsed JSON response
        """
        if not frames:
            return VLMResult(
                raw_response="",
                success=False,
                error="No frames provided",
            )

        # Circuit breaker: skip if OVMS is known to be broken
        cb_result = await self._check_circuit_breaker()
        if cb_result is not None:
            return cb_result

        messages = self._build_messages(frames, prompt)

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stop": ["}"],
        }

        url = f"{self.endpoint}/v3/chat/completions"

        t0 = time.perf_counter()
        try:
            response = await self._http_client.post(url, json=payload)
            response.raise_for_status()

            data = response.json()
            raw_text = data["choices"][0]["message"]["content"]
            latency_ms = (time.perf_counter() - t0) * 1000.0

            usage = data.get("usage") or {}
            logger.info(
                "VLM call latency=%.0fms model=%s frames=%d prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                latency_ms,
                self.model_name,
                len(frames),
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("total_tokens"),
            )
            logger.debug(f"VLM raw response: {raw_text}")

            # Try to parse as JSON
            parsed = self._parse_json_response(raw_text)

            self._record_success()
            return VLMResult(
                raw_response=raw_text,
                parsed=parsed,
                success=parsed is not None,
                metrics={
                    "latency_ms": round(latency_ms, 1),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "model": self.model_name,
                    "num_frames": len(frames),
                },
            )

        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning(
                "VLM request timed out after %.0fms (timeout=%ss, frames=%d)",
                latency_ms, self.timeout, len(frames),
            )
            self._record_failure("timeout")
            return VLMResult(
                raw_response="",
                success=False,
                error="VLM request timed out",
            )
        except httpx.HTTPStatusError as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.error(
                "VLM HTTP error %s after %.0fms",
                e.response.status_code, latency_ms,
            )
            self._record_failure(f"HTTP {e.response.status_code}")
            return VLMResult(
                raw_response="",
                success=False,
                error=f"HTTP {e.response.status_code}",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("VLM request failed after %.0fms: %s", latency_ms, e)
            self._record_failure(str(e))
            return VLMResult(
                raw_response="",
                success=False,
                error=str(e),
            )

    @staticmethod
    def _parse_json_response(text: str) -> Optional[dict]:
        """
        Extract and parse JSON from VLM response text.

        Handles responses that may have markdown code blocks or
        extra text around the JSON.  Also handles truncation from
        stop=["}"] which strips the closing brace.
        """
        text = text.strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # If stop token stripped the closing brace, re-add it
        if text.startswith("{") and not text.endswith("}"):
            try:
                return json.loads(text + "}")
            except json.JSONDecodeError:
                pass

        # Try extracting from markdown code block
        if "```" in text:
            for block in text.split("```"):
                block = block.strip()
                if block.startswith("json"):
                    block = block[4:].strip()
                try:
                    return json.loads(block)
                except json.JSONDecodeError:
                    continue

        # Try finding JSON object in text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse JSON from VLM response: {text[:200]}")
        return None
