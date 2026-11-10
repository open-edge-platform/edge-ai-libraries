import logging
import threading
import time
from typing import Optional

import httpx

from dlsps2_runner import DLSPS2_BASE_URL, DLSPS2_HTTP_TIMEOUT_S, DLSPS2_VERIFY_TLS

# Attempts, and seconds between them, to read the element list when it is first needed.
ELEMENTS_READ_ATTEMPTS = 5
ELEMENTS_RETRY_DELAY_S = 2.0


class GstInspector:
    """
    Thread-safe singleton class listing the GStreamer elements of DLSPS 2.0.

    Pipelines run on DLSPS 2.0, so the elements that may be used in them are
    those of the server: they are read from its ``GET /elements``, which
    reports what ``gst-inspect-1.0`` lists in the server's runtime. If the
    server cannot be read, the list stays empty, an error is logged, and the
    next read of :attr:`elements` tries again.

    Implements singleton pattern using __new__ with double-checked locking.

    Elements are returned as a sorted list of ``(plugin, element, description)``
    tuples:

    [
        ("videoanalytics", "gvaclassify", "<description>"),
        ("videoanalytics", "gvadetect", "<description>"),
        ("videoanalytics", "gvainference", "<description>")
    ]
    """

    _instance: Optional["GstInspector"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "GstInspector":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self.logger = logging.getLogger("GstInspector")
        self._elements_lock = threading.Lock()
        self._elements = self._get_gst_elements(attempts=ELEMENTS_READ_ATTEMPTS)

    @property
    def elements(self) -> list[tuple[str, str, str]]:
        """The server's elements, read again while the list is empty."""
        if not self._elements:
            with self._elements_lock:
                if not self._elements:
                    self._elements = self._get_gst_elements()
        return self._elements

    def _get_gst_elements(self, attempts: int = 1) -> list[tuple[str, str, str]]:
        for attempt in range(attempts):
            if attempt:
                time.sleep(ELEMENTS_RETRY_DELAY_S)
            elements = self._get_dlsps2_elements()
            if elements:
                return elements
        self.logger.error(
            "No GStreamer elements from DLSPS 2.0 at %s; decoder and encoder "
            "selection has no element list until the server answers.",
            DLSPS2_BASE_URL,
        )
        return []

    def _get_dlsps2_elements(self) -> list[tuple[str, str, str]]:
        try:
            response = httpx.get(
                f"{DLSPS2_BASE_URL}/elements",
                timeout=DLSPS2_HTTP_TIMEOUT_S,
                verify=DLSPS2_VERIFY_TLS,
            )
            response.raise_for_status()
            return sorted(
                (e["plugin"], e["name"], e["description"]) for e in response.json()
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            self.logger.error(f"Error reading elements from DLSPS 2.0: {e}")
            return []

    def get_elements(self) -> list[tuple[str, str, str]]:
        return self.elements
