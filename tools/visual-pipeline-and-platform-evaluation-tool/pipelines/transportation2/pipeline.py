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
            # Input
            "filesrc "
            "  location={VIDEO_PATH} ! "
            "qtdemux ! "
            "h264parse ! "
            # Decoder
            "{decoder} ! "
            # Detection
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "gvadetect "
            "  {detection_model_config} "
            "  model-instance-id=detect0 "
            "  pre-process-backend={object_detection_pre_process_backend} "
            "  device={object_detection_device} "
            "  batch-size={object_detection_batch_size} "
            "  inference-interval={object_detection_inference_interval} "
            "  nireq={object_detection_nireq} ! "
            # Tracking
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "gvatrack "
            "  tracking-type=short-term-imageless ! "
            # Classification
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
            # Metadata
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "gvawatermark ! "
            "gvafpscounter ! "
            "gvametaconvert "
            "  format=json "
            "  json-indent=4 "
            "  source={VIDEO_PATH} ! "
            "gvametapublish "
            "  method=file "
            "  file-path=/dev/null ! "
            # Output
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "{encoder} ! "
            "h264parse ! "
            "mp4mux ! "
            "filesink "
            "  location={VIDEO_OUTPUT_PATH}"
        )

    def evaluate(
        self,
        constants: dict,
        parameters: dict,
        regular_channels: int,
        inference_channels: int,
        elements: list = None,
    ) -> str:
        # Set pre process backed for object detection
        parameters["object_detection_pre_process_backend"] = (
            "opencv"
            if parameters["object_detection_device"] in ["CPU", "NPU"]
            else "va-surface-sharing"
        )

        # Set pre process backed for object classification
        parameters["object_classification_pre_process_backend"] = (
            "opencv"
            if parameters["object_classification_device"] in ["CPU", "NPU"]
            else "va-surface-sharing"
        )

        # Find the available decoder and encoder dynamically
        if (
            parameters["object_detection_device"].startswith("GPU.")
            and int(parameters["object_detection_device"].split(".")[1]) > 0
        ):
            gpu_index = parameters["object_detection_device"].split(".")[1]
            # Map GPU index to the corresponding VAAPI element suffix (e.g., "129" for GPU.1)
            vaapi_suffix = str(
                128 + int(gpu_index)
            )  # 128 + 1 = 129, 128 + 2 = 130, etc.
            _encoder_element = f"varenderD{vaapi_suffix}h264lpenc"
            _decoder_element = (
                f"varenderD{vaapi_suffix}h264dec ! video/x-raw(memory:VAMemory)"
            )
        else:
            _encoder_element = next(
                ("vah264lpenc" for element in elements if element[1] == "vah264lpenc"),
                next(
                    ("vah264enc" for element in elements if element[1] == "vah264enc"),
                    next(
                        (
                            "x264enc bitrate=16000 speed-preset=superfast"
                            for element in elements
                            if element[1] == "x264enc"
                        ),
                        None,  # Fallback to None if no encoder is found
                    ),
                ),
            )
            _decoder_element = next(
                (
                    "vah264dec ! video/x-raw(memory:VAMemory)"
                    for element in elements
                    if element[1] == "vah264dec"
                ),
                next(
                    ("decodebin" for element in elements if element[1] == "decodebin"),
                    None,  # Fallback to None if no decoder is found
                ),
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
                    decoder=_decoder_element,
                    encoder=_encoder_element,
                    detection_model_config=detection_model_config,
                    classification_model_config=classification_model_config,
                )
            ]
            # Only inference channels are used for the pipeline
            # Ignore regular channels
            * (inference_channels)
        )
