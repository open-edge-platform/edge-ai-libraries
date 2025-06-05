from pathlib import Path
from pipeline import GstPipeline

class Transportation2Pipeline(GstPipeline):
    def __init__(self):
        super().__init__()

        self._diagram = Path("transportation2.drawio.png")

        self._bounding_boxes = [
            (266, 10, 386, 70, "Object Detection", "Object Detection"),
            (559, 10, 739, 70, "Object Classification", "Object classification"),
        ]

        self._pipeline = (
            "filesrc "
            "  location={VIDEO_PATH} ! "
            "decodebin ! "
            "queue ! "
            "gvadetect "
            "  model={OBJECT_DETECTION_MODEL_PATH} "
            "  model-proc={OBJECT_DETECTION_MODEL_PROC} "
            "  inference-interval=3 "
            "  threshold=0.4 "
            "  device={object_detection_device} ! "
            "queue ! "
            "gvatrack "
            "  tracking-type=short-term-imageless ! "
            "gvaclassify "
            "  model={VEHICLE_CLASSIFICATION_MODEL_PATH} "
            "  model-proc={VEHICLE_CLASSIFICATION_MODEL_PROC} "
            "  reclassify-interval=10 "
            "  device={vehicle_classification_device} "
            "  object-class=vehicle ! "
            "queue ! "
            "gvawatermark ! "
            "videoconvert ! "
            "gvafpscounter ! "
            "gvametaconvert "
            "  add-tensor-data=false ! "
            "gvametapublish "
            "  method=file "
            "  file-path=/dev/null ! "
            "queue ! "
            "x264enc ! "
            "mp4mux ! "
            "filesink "
            "  location={VIDEO_OUTPUT_PATH}"
        )

    def evaluate(
        self,
        constants: dict,
        parameters: dict,
        regular_channels: int,
        inference_channels,
    ) -> str:
        #  if (channels > 1):
        # Replace  "queue ! x264enc ! mp4mux ! filesink location={VIDEO_OUTPUT_PATH}
        # With fakesink

        return "gst-launch-1.0 -q " + " ".join(
            [self._pipeline.format(**parameters, **constants)]
            * (regular_channels + inference_channels)
        )
