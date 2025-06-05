import os
from pathlib import Path

from pipeline import GstPipeline


class Transportation2Pipeline(GstPipeline):
    def __init__(self):
        super().__init__()

        self._diagram = Path(os.path.dirname(__file__)) / "diagram.png"

        self._bounding_boxes = [
            (331, 182, 451, 242, "Inference", "Inference"),
        ]

        self._pipeline = (
            "filesrc "
            "  location={VIDEO_PATH} ! "
            "decodebin ! "
            "queue2 max-size-bytes=0 max-size-time=0 ! "
            "gvadetect "
            "  {detection_model_config} "
            "  model-instance-id=detect0 "
            "  pre-process-backend={object_detection_pre_process_backend} "
            "  device={object_detection_device} "
            "  batch-size={object_detection_batch_size} "
            "  inference-interval={object_detection_inference_interval} "
            "  nireq={object_detection_nireq} ! "
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "gvatrack "
            "  tracking-type=short-term-imageless ! "
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "gvaclassify "
            "  {classification_model_config} "
            "  model-instance-id=classify0 "
            "  pre-process-backend={object_classification_pre_process_backend} "
            "  device={object_classification_device} "
            "  batch-size={object_classification_batch_size} "
            "  inference-interval={object_classification_inference_interval} "
            "  nireq={object_classification_nireq} "
            "  reclassify-interval={object_classification_reclassify_interval} ! "
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "gvawatermark ! "
            "videoconvert ! "
            "gvafpscounter ! "
            "gvametaconvert "
            "  format=json "
            "  json-indent=4 "
            "  source={VIDEO_PATH} ! "
            "gvametapublish "
            "  method=file "
            "  file-path=/dev/null ! "
            "queue2 max-size-bytes=0 max-size-time=0 ! "
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
        elements: list = None,
    ) -> str:
        # Set pre process backed for object detection
        parameters["object_detection_pre_process_backend"] = (
            "opencv"
            # TODO: Implement GPU Support in the pipeline
            # if parameters["object_detection_device"] in ["CPU", "NPU"]
            # else "va-surface-sharing"
        )

        # Set pre process backed for object classification
        parameters["object_classification_pre_process_backend"] = (
            "opencv"
            # TODO: Implement GPU Support in the pipeline
            # if parameters["object_classification_device"] in ["CPU", "NPU"]
            # else "va-surface-sharing"
        )

        # Set model config for object detection
        detection_model_config = (
            f"model={constants["OBJECT_DETECTION_MODEL_PATH"]} "
            f"model-proc={constants["OBJECT_DETECTION_MODEL_PROC"]} "
        )

        if not constants["OBJECT_DETECTION_MODEL_PROC"]:
            detection_model_config = (
                f"model={constants["OBJECT_DETECTION_MODEL_PATH"]} "
            )

        # Set model config for object classification
        classification_model_config = (
            f"model={constants["OBJECT_CLASSIFICATION_MODEL_PATH"]} "
            f"model-proc={constants["OBJECT_CLASSIFICATION_MODEL_PROC"]} "
        )

        if not constants["OBJECT_CLASSIFICATION_MODEL_PROC"]:
            classification_model_config = (
                f"model={constants["OBJECT_CLASSIFICATION_MODEL_PATH"]} "
            )

        return "gst-launch-1.0 -q " + " ".join(
            [
                self._pipeline.format(
                    **parameters,
                    **constants,
                    detection_model_config=detection_model_config,
                    classification_model_config=classification_model_config,
                )
            ]
            # TODO: Handle regular channels?
            * (inference_channels)
        )
