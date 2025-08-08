import logging
import os
from pathlib import Path
import struct

from gstpipeline import GstPipeline
from utils import get_video_resolution, UINT8_DTYPE_SIZE, VIDEO_STREAM_META_PATH


class SimpleVideoStructurizationPipeline(GstPipeline):
    def __init__(self):
        super().__init__()

        self._diagram = Path(os.path.dirname(__file__)) / "diagram.png"

        self._inference_stream_decode_detect_track = (
            # Input
            "filesrc location={VIDEO_PATH} ! "
            # Decoder
            "{decoder} ! "
            # Detection
            "gvafpscounter starting-frame=500 ! "
            "gvadetect "
            "   {detection_model_config} "
            "   model-instance-id=detect0 "
            "   device={object_detection_device} "
            "   pre-process-backend={object_detection_pre_process_backend} "
            "   batch-size={object_detection_batch_size} "
            "   inference-interval={object_detection_inference_interval} "
            "   nireq={object_detection_nireq} ! "
            "queue ! "
            "gvatrack "
            "  tracking-type=short-term-imageless ! "
            "queue ! "
        )

        self._inference_stream_classify = (
            "gvaclassify "
            "   {classification_model_config} "
            "   model-instance-id=classify0 "
            "   device={object_classification_device} "
            "   pre-process-backend={object_classification_pre_process_backend} "
            "   batch-size={object_classification_batch_size} "
            "   inference-interval={object_classification_inference_interval} "
            "   nireq={object_classification_nireq} "
            "   reclassify-interval={object_classification_reclassify_interval} ! "
            "queue ! "
        )

        self._inference_output_stream = (
            "{encoder} ! "
            "h264parse ! "
            "mp4mux ! "
            "filesink "
            "  location={VIDEO_OUTPUT_PATH} "
        )

        # Add shmsink for live preview (shared memory)
        self._shmsink = (
            "shmsink socket-path=/tmp/shared_memory/video_stream "
            "wait-for-connection=false "
            "sync=true "
            "name=shmsink0 "
        )

        # shmsink branch for live preview (BGR format), width/height will be formatted in evaluate
        self._shmsink_branch = (
            "tee name=livetee "
            "livetee. ! queue2 ! {encoder} ! h264parse ! mp4mux ! filesink location={VIDEO_OUTPUT_PATH} async=false "
            "livetee. ! queue2 ! videoconvert ! video/x-raw,format=BGR,width={width},height={height} ! {shmsink} "
        )

    def evaluate(
        self,
        constants: dict,
        parameters: dict,
        regular_channels: int,
        inference_channels: int,
        elements: list = None,
    ) -> str:

        # Set decoder element based on device
        _decoder_element = (
            "decodebin3 "
            if parameters["object_detection_device"] in ["CPU", "NPU"]
            else "decodebin3 ! vapostproc ! video/x-raw\\(memory:VAMemory\\)"
        )

        # Set encoder element based on device
        _encoder_element = next(
            ("vah264enc" for element in elements if element[1] == "vah264enc"),
            next(
                ("vah264lpenc" for element in elements if element[1] == "vah264lpenc"),
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

        # Set model config for object detection
        detection_model_config = (
            f"model={constants["OBJECT_DETECTION_MODEL_PATH"]} "
            f"model-proc={constants["OBJECT_DETECTION_MODEL_PROC"]} "
        )

        if not constants["OBJECT_DETECTION_MODEL_PROC"]:
            detection_model_config = (
                f"model={constants["OBJECT_DETECTION_MODEL_PATH"]} "
            )

        streams = ""

        # Prepare shmsink and meta if live_preview_enabled
        if parameters["live_preview_enabled"]:
            # Get resolution using get_video_resolution
            video_path = constants.get("VIDEO_PATH", "")
            width, height = get_video_resolution(video_path)
            # Write meta file for live preview
            try:
                os.makedirs("/tmp/shared_memory", exist_ok=True)
                with open(VIDEO_STREAM_META_PATH, "wb") as f:
                    # height, width, dtype_size=UINT8_DTYPE_SIZE (uint8)
                    f.write(struct.pack("III", height, width, UINT8_DTYPE_SIZE))
            except Exception as e:
                logging.warning(f"Could not write shared memory meta file: {e}")

        for i in range(inference_channels):
            streams += self._inference_stream_decode_detect_track.format(
                **parameters,
                **constants,
                decoder=_decoder_element,
                detection_model_config=detection_model_config,
            )

            # Handle object classification parameters and constants
            # Do this only if the object classification model is not disabled or the device is not disabled
            if not (constants["OBJECT_CLASSIFICATION_MODEL_PATH"] == "Disabled"
                    or parameters["object_classification_device"] == "Disabled"):
                # Set model config for object classification
                classification_model_config = (
                    f"model={constants["OBJECT_CLASSIFICATION_MODEL_PATH"]} "
                    f"model-proc={constants["OBJECT_CLASSIFICATION_MODEL_PROC"]} "
                )

                if not constants["OBJECT_CLASSIFICATION_MODEL_PROC"]:
                    classification_model_config = (
                        f"model={constants["OBJECT_CLASSIFICATION_MODEL_PATH"]} "
                    )

                streams += self._inference_stream_classify.format(
                    **parameters,
                    **constants,
                    classification_model_config=classification_model_config,
                )

            # Overlay inference results on the inferred video if enabled
            if parameters["pipeline_watermark_enabled"] and parameters["pipeline_video_enabled"]:
                streams += "gvawatermark ! "

            # Use video output for the first inference channel if enabled, otherwise use fakesink
            if i == 0 and (parameters["pipeline_video_enabled"] or parameters["live_preview_enabled"]):
                if parameters["live_preview_enabled"]:
                    # Use tee to split to both file and shmsink, fill in width/height here
                    streams += self._shmsink_branch.format(
                        **constants,
                        encoder=_encoder_element,
                        width=width,
                        height=height,
                        shmsink=self._shmsink
                    )
                else:
                    streams += self._inference_output_stream.format(**constants, encoder=_encoder_element)
            else:
                streams += "fakesink "

        return "gst-launch-1.0 -q " + streams
