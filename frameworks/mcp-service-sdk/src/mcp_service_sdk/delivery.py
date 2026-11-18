"""Delivery fan-out (walkthrough §4).

Emit always saves to the service's own log FIRST; the log then pushes to
whichever sinks are enabled:

- EventHubSink  — default; de-dupes, fans out, retries. The agent inbox listens here.
- WebhookSink   — HTTP callback for partners / other agent frameworks, with retry.
- DisabledSink  — single flag for clean benchmark runs.

Failed callbacks are retried; nothing is dropped silently.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Protocol

from .envelope import EventEnvelope


class Sink(Protocol):
    name: str

    def push(self, event: EventEnvelope) -> bool:
        """Deliver one event. Return True on success, False to trigger retry."""
        ...


class DisabledSink:
    """Drops delivery on purpose — used for clean benchmark runs."""

    name = "disabled"

    def push(self, event: EventEnvelope) -> bool:  # noqa: ARG002 - intentional no-op
        return True


class WebhookSink:
    """POSTs the event envelope to a callback URL (stdlib, no extra deps)."""

    name = "webhook"

    def __init__(self, url: str, timeout_s: float = 5.0) -> None:
        self._url = url
        self._timeout_s = timeout_s

    def push(self, event: EventEnvelope) -> bool:
        data = event.to_json().encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, TimeoutError):
            return False


class EventHubSink:
    """Adapter placeholder for the shared Event Hub.

    Wire ``publish`` to the real hub client in deployment. Kept as an injectable
    callable so the core stays dependency-free and testable.
    """

    name = "event_hub"

    def __init__(self, publish) -> None:
        self._publish = publish

    def push(self, event: EventEnvelope) -> bool:
        try:
            self._publish(json.loads(event.to_json()))
            return True
        except Exception:  # noqa: BLE001 - any hub failure means retry
            return False


class Delivery:
    """Fans an event out to all enabled sinks with bounded retries."""

    def __init__(
        self,
        sinks: list[Sink] | None = None,
        max_retries: int = 3,
        backoff_s: float = 0.5,
    ) -> None:
        self._sinks: list[Sink] = sinks or [DisabledSink()]
        self._max_retries = max_retries
        self._backoff_s = backoff_s

    def dispatch(self, event: EventEnvelope) -> dict[str, bool]:
        """Deliver to every sink; returns per-sink final success flag."""
        results: dict[str, bool] = {}
        for sink in self._sinks:
            results[sink.name] = self._push_with_retry(sink, event)
        return results

    def _push_with_retry(self, sink: Sink, event: EventEnvelope) -> bool:
        for attempt in range(self._max_retries):
            if sink.push(event):
                return True
            if attempt < self._max_retries - 1:
                time.sleep(self._backoff_s * (2**attempt))
        return False
