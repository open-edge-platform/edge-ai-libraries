import subprocess
from threading import Lock


class GstInspector:
    """
    A singleton class to inspect GStreamer elements using gst-inspect-1.0.
    This class provides a method to retrieve the list of GStreamer elements
    and their descriptions.

    These is an example of the output from the command:

    videoanalytics:  gvaclassify: Object classification (requires GstVideoRegionOfInterestMeta on input)
    videoanalytics:  gvadetect: Object detection (generates GstVideoRegionOfInterestMeta)
    videoanalytics:  gvainference: Generic full-frame inference (generates GstGVATensorMeta)

    Those elements will be returned in a list of tuples:

    [
        ("videoanalytics", "gvaclassify", "<description>"),
        ("videoanalytics", "gvadetect", "<description>"),
        ("videoanalytics", "gvainference", "<description>")
    ]
    """

    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GstInspector, cls).__new__(cls)
                cls._instance._initialize()
        return cls._instance

    def _initialize(self):
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

        except subprocess.CalledProcessError as e:
            print(f"Error running gst-inspect-1.0: {e}")
            return []

    def get_elements(self):
        return self.elements
