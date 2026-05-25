"""Thread-safe last-call latency tracker."""
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


tts_latency = LatencyStore()
