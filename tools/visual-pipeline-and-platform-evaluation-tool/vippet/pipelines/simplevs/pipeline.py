import logging
import os
from pathlib import Path
import struct

from gstpipeline import GstPipeline
from utils import (
    get_video_resolution,
    UINT8_DTYPE_SIZE,
    VIDEO_STREAM_META_PATH,
    is_yolov10_model,
)


class SimpleVideoStructurizationPipeline(GstPipeline):
    def __init__(self):
        super().__init__()

        self._diagram = Path(os.path.dirname(__file__)) / "diagram.png"

        self._bounding_boxes = [
            (330, 110, 445, 170, "Inference", "Object Detection"),
        ]

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
            "   {ie_config_parameter} "
            "   nireq={object_detection_nireq} ! "
            "queue ! "
            "gvatrack "
            "  tracking-type={tracking_type} ! "
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

        self._inference_stream_metadata_processing = (
            "gvametaconvert "
            "  format=json "
            "  json-indent=4 "
            "  source={VIDEO_PATH} ! "
            "gvametapublish "
            "  method=file "
            "  file-path=/dev/null ! "
        )

        self._inference_output_stream = "{encoder} ! {VIDEO_CODEC}parse ! mp4mux ! filesink location={VIDEO_OUTPUT_PATH} "

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
            "livetee. ! queue2 ! {encoder} ! {VIDEO_CODEC}parse ! mp4mux ! filesink location={VIDEO_OUTPUT_PATH} async=false "
            "livetee. ! queue2 ! videoconvert ! video/x-raw,format=BGR,width={width},height={height} ! {shmsink} "
        )

    def evaluate(
        self,
        constants: dict,
        parameters: dict,
        regular_channels: int,
        inference_channels: int,
        elements: list | None = None,
    ) -> str:
        if elements is None:
            elements = []

        # Set decoder element based on device
        _decoder_element = (
            "decodebin3 "
            if parameters["object_detection_device"] in ["CPU", "NPU"]
            else "decodebin3 ! vapostproc ! video/x-raw\\(memory:VAMemory\\)"
        )

        # Set encoder element based on device
        _codec_bits = constants["VIDEO_CODEC"].lstrip("h")  # e.g., "h264" -> "264"
        _encoder_element = next(
            (
                f"va{constants['VIDEO_CODEC']}enc"
                for element in elements
                if element[1] == f"va{constants['VIDEO_CODEC']}enc"
            ),
            next(
                (
                    f"va{constants['VIDEO_CODEC']}lpenc"
                    for element in elements
                    if element[1] == f"va{constants['VIDEO_CODEC']}lpenc"
                ),
                next(
                    (
                        f"x{_codec_bits}enc bitrate=16000 speed-preset=superfast"
                        for element in elements
                        if element[1] == f"x{_codec_bits}enc"
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
            f"model={constants['OBJECT_DETECTION_MODEL_PATH']} "
            f"model-proc={constants['OBJECT_DETECTION_MODEL_PROC']} "
        )

        if not constants["OBJECT_DETECTION_MODEL_PROC"]:
            detection_model_config = (
                f"model={constants['OBJECT_DETECTION_MODEL_PATH']} "
            )

        # Set inference config parameter for GPU if using YOLOv10
        ie_config_parameter = ""
        if parameters["object_detection_device"] == "GPU" and is_yolov10_model(
            constants["OBJECT_DETECTION_MODEL_PATH"]
        ):
            ie_config_parameter = "ie-config=GPU_DISABLE_WINOGRAD_CONVOLUTION=YES"

        streams = ""

        # Prepare shmsink and meta if live_preview_enabled
        width = 0
        height = 0
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
                ie_config_parameter=ie_config_parameter,
            )

            # Handle object classification parameters and constants
            # Do this only if the object classification model is not disabled or the device is not disabled
            if not (
                constants["OBJECT_CLASSIFICATION_MODEL_PATH"] == "Disabled"
                or parameters["object_classification_device"] == "Disabled"
            ):
                # Set model config for object classification
                classification_model_config = (
                    f"model={constants['OBJECT_CLASSIFICATION_MODEL_PATH']} "
                    f"model-proc={constants['OBJECT_CLASSIFICATION_MODEL_PROC']} "
                )

                if not constants["OBJECT_CLASSIFICATION_MODEL_PROC"]:
                    classification_model_config = (
                        f"model={constants['OBJECT_CLASSIFICATION_MODEL_PATH']} "
                    )

                streams += self._inference_stream_classify.format(
                    **parameters,
                    **constants,
                    classification_model_config=classification_model_config,
                )

            # Overlay inference results on the inferred video if enabled
            if (
                parameters["pipeline_watermark_enabled"]
                and parameters["pipeline_video_enabled"]
            ):
                streams += "gvawatermark ! "

            # Metadata processing and publishing
            streams += self._inference_stream_metadata_processing.format(
                **parameters,
                **constants,
            )

            # Use video output for the first inference channel if enabled, otherwise use fakesink
            if i == 0 and (
                parameters["pipeline_video_enabled"]
                or parameters["live_preview_enabled"]
            ):
                if parameters["live_preview_enabled"]:
                    # Use tee to split to both file and shmsink, fill in width/height here
                    streams += self._shmsink_branch.format(
                        **constants,
                        encoder=_encoder_element,
                        width=width,
                        height=height,
                        shmsink=self._shmsink,
                    )
                else:
                    streams += self._inference_output_stream.format(
                        **constants, encoder=_encoder_element
                    )
            else:
                streams += "fakesink "

        return streams

    def get_default_gst_launch(
        self,
        elements: list | None = None,
    ) -> str:
        # Provide default parameters for a basic pipeline
        default_params = {
            "object_detection_device": "CPU",
            "object_detection_batch_size": 0,
            "object_detection_inference_interval": 3,
            "object_detection_nireq": 0,
            "object_classification_device": "CPU",
            "object_classification_batch_size": 0,
            "object_classification_inference_interval": 3,
            "object_classification_nireq": 0,
            "object_classification_reclassify_interval": 1,
            "tracking_type": "short-term-imageless",
            "pipeline_watermark_enabled": True,
            "pipeline_video_enabled": True,
            "live_preview_enabled": False,
        }

        # Provide default constants for a basic pipeline
        default_constants = {
            "VIDEO_PATH": "/tmp/dummy-video.mp4",
            "VIDEO_CODEC": "h264",
            "VIDEO_OUTPUT_PATH": "/tmp/dummy-video-output.mp4",
            "OBJECT_DETECTION_MODEL_PATH": "/models/output/public/yolov8_license_plate_detector/FP32/yolov8_license_plate_detector.xml",
            "OBJECT_DETECTION_MODEL_PROC": "",
            "OBJECT_CLASSIFICATION_MODEL_PATH": "/models/output/public/ch_PP-OCRv4_rec_infer/FP32/ch_PP-OCRv4_rec_infer.xml",
            "OBJECT_CLASSIFICATION_MODEL_PROC": "",
        }

        # Set default number of channels
        regular_channels = 0
        inference_channels = 1

        # Use the full evaluate method with default parameters
        return self.evaluate(
            default_constants,
            default_params,
            regular_channels,
            inference_channels,
            elements,
        )
