import logging
import subprocess
import threading
from typing import Optional


class GstInspector:
    """
    Thread-safe singleton class to inspect GStreamer elements using gst-inspect-1.0.

    This class provides a method to retrieve the list of GStreamer elements
    and their descriptions. Implements singleton pattern using __new__ with
    double-checked locking.

    Example output from gst-inspect-1.0:

    videoanalytics:  gvaclassify: Object classification (requires GstVideoRegionOfInterestMeta on input)
    videoanalytics:  gvadetect: Object detection (generates GstVideoRegionOfInterestMeta)
    videoanalytics:  gvainference: Generic full-frame inference (generates GstGVATensorMeta)

    Elements are returned as a list of tuples:

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
        self.elements = self._get_gst_elements()

    def _get_gst_elements(self):
        try:
            result = subprocess.run(
                ["gst-inspect-1.0"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            lines = result.stdout.splitlines()
            elements = []
            for line in lines:
                if ":  " in line:
                    plugin, rest = line.split(":  ", 1)
                    if ": " in rest:
                        element, description = rest.split(": ", 1)
                        elements.append(
                            (plugin.strip(), element.strip(), description.strip())
                        )

            return sorted(elements)

        except Exception as e:
            self.logger.error(f"Error running gst-inspect-1.0: {e}")
            return []

    def get_elements(self):
        return self.elements
