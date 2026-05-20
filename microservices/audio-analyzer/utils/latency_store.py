"""Thread-safe last-call latency tracker.

A single module-level instance (``asr_latency``) is imported by both the
pipeline (which records measurements) and the API layer (which exposes them).
"""
import threading


class LatencyStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: float | None = None

    def record(self, latency_ms: float) -> None:
        with self._lock:
            self._last = round(latency_ms, 1)

    def stats(self) -> dict:
        with self._lock:
            return {"last_ms": self._last}


# Module-level singleton shared by pipeline and API
asr_latency = LatencyStore()
