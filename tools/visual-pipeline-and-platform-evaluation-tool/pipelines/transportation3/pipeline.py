import os
from pathlib import Path

from pipeline import GstPipeline


class LicensePlateDetectionPipeline(GstPipeline):
    def __init__(self):
        super().__init__()

        self._diagram = Path(os.path.dirname(__file__)) / "diagram.png"

        self._bounding_boxes = [
            (331, 100, 451, 160, "Inference", "Inference"),
        ]

        self._pipeline = (
            # Input
            "filesrc location={VIDEO_PATH} ! "
             # Decoder
            "decodebin ! "
            "vapostproc ! "
            "\"video/x-raw(memory:VAMemory)\",format=NV12 ! "
            # Detection
            "gvadetect "
            "   model=\"/home/dlstreamer/vippet/models/public/yolov8_license_plate_detector/FP16/yolov8_license_plate_detector.xml\" "
            "   device=GPU "
            "   pre-process-backend=va-surface-sharing ! "
            "queue ! "
            "videoconvert ! "
            # Classification
            "gvaclassify "
            "   model=\"/home/dlstreamer/vippet/models/public/ch_PP-OCRv4_rec_infer/FP16/ch_PP-OCRv4_rec_infer.xml\" "
            "   device=GPU "
            "   pre-process-backend=opencv ! "
            "queue ! "
            # Metadata
            "gvametaconvert "
            "   format=json ! "
            "gvametapublish "
            "   file-format=json-lines "
            "   file-path=\"/tmp/output1.json\" ! "
            "gvafpscounter ! "
            # Output
            "fakesink"
        )

    def evaluate(
        self,
        constants: dict,
        parameters: dict,
        elements: list = None,
    ) -> str:
        
        return "gst-launch-1.0 -q " + " ".join(
            [
                self._pipeline.format(
                    **parameters,
                    **constants,
                )
            ]
            * (constants['channels'] if constants.get('channels') else 1)
        )
