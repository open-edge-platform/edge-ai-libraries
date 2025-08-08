import logging
import math
import os
from pathlib import Path
import struct

from gstpipeline import GstPipeline
from utils import UINT8_DTYPE_SIZE, VIDEO_STREAM_META_PATH


class SmartNVRPipeline(GstPipeline):
    def __init__(self):
        super().__init__()

        self._diagram = Path(os.path.dirname(__file__)) / "diagram.png"

        self._bounding_boxes = [
            (325, 108, 445, 168, "Inference", "Object Detection"),
        ]

        self._sink = (
            "sink_{id}::xpos={xpos} " "sink_{id}::ypos={ypos} " "sink_{id}::alpha=1 "
        )

        # Add shmsink for live streaming (shared memory)
        self._shmsink = (
            "shmsink socket-path=/tmp/shared_memory/video_stream "
            "wait-for-connection=false "
            "sync=true "
            "name=shmsink0 "
        )

        # Use tee to split output to both file and live stream
        self._compositor_with_tee = (
            "{compositor} "
            "  name=comp "
            "  {sinks} ! tee name=livetee "
            "livetee. ! queue2 ! {encoder} ! h264parse ! mp4mux ! filesink location={VIDEO_OUTPUT_PATH} async=false "
            "livetee. ! queue2 ! videoconvert ! video/x-raw,format=BGR,width={output_width},height={output_height} ! {shmsink} "
        )

        self._compositor = (
            "{compositor} "
            "  name=comp "
            "  {sinks} ! "
            "{encoder} ! "
            "h264parse ! "
            "mp4mux ! "
            "filesink "
            "  location={VIDEO_OUTPUT_PATH} async=false "
        )

        self._recording_stream = (
            "filesrc "
            "  location={VIDEO_PATH} ! "
            "qtdemux ! "
            "h264parse ! "
            "tee name=t{id} ! "
            "queue2 ! "
            "mp4mux ! "
            "filesink "
            "  location=/tmp/stream{id}.mp4 "
            "t{id}. ! "
            "queue2 ! "
            "{decoder} ! "
            "gvafpscounter starting-frame=500 ! "
        )

        self._inference_stream_decode_detect_track = (
            "filesrc "
            "  location={VIDEO_PATH} ! "
            "qtdemux ! "
            "h264parse ! "
            "tee name=t{id} ! "
            "queue2 ! "
            "mp4mux ! "
            "filesink "
            "  location=/tmp/stream{id}.mp4 "
            "t{id}. ! "
            "queue2 ! "
            "{decoder} ! "
            "gvafpscounter starting-frame=500 ! "
            "gvadetect "
            "  {detection_model_config} "
            "  model-instance-id=detect0 "
            "  pre-process-backend={object_detection_pre_process_backend} "
            "  device={object_detection_device} "
            "  batch-size={object_detection_batch_size} "
            "  inference-interval={object_detection_inference_interval} "
            "  nireq={object_detection_nireq} ! "
            "queue2 ! "
            "gvatrack "
            "  tracking-type=short-term-imageless ! "
            "queue2 ! "
        )

        self._inference_stream_classify = (
            "gvaclassify "
            "  {classification_model_config} "
            "  model-instance-id=classify0 "
            "  pre-process-backend={object_classification_pre_process_backend} "
            "  device={object_classification_device} "
            "  batch-size={object_classification_batch_size} "
            "  inference-interval={object_classification_inference_interval} "
            "  nireq={object_classification_nireq} "
            "  reclassify-interval={object_classification_reclassify_interval} ! "
            "queue2 ! "
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

        self._sink_to_compositor = (
            "queue2 "
            "  max-size-buffers={max_size_buffers} "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "{postprocessing} ! "
            "video/x-raw,width=640,height=360 ! "
            "comp.sink_{id} "
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

        # Compute total number of channels
        channels = regular_channels + inference_channels

        # Create a sink for each channel
        sinks = ""
        grid_size = math.ceil(math.sqrt(channels))
        for i in range(channels):
            xpos = 640 * (i % grid_size)
            ypos = 360 * (i // grid_size)
            sinks += self._sink.format(id=i, xpos=xpos, ypos=ypos)

        # Find the available compositor in elements dynamically
        if (
            parameters["object_detection_device"].startswith("GPU.")
            and int(parameters["object_detection_device"].split(".")[1]) > 0
        ):
            gpu_index = parameters["object_detection_device"].split(".")[1]
            # Map GPU index to the corresponding VAAPI element suffix (e.g., "129" for GPU.1)
            vaapi_suffix = str(
                128 + int(gpu_index)
            )  # 128 + 1 = 129, 128 + 2 = 130, etc.
            _compositor_element = f"varenderD{vaapi_suffix}compositor"
        else:
            _compositor_element = next(
                (
                    "vacompositor"
                    for element in elements
                    if element[1] == "vacompositor"
                ),
                next(
                    (
                        "compositor"
                        for element in elements
                        if element[1] == "compositor"
                    ),
                    None,  # Fallback to None if no compositor is found
                ),
            )

        # Find the available encoder dynamically
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
        else:
            # Fallback to default encoder if no specific GPU is selected
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

        # Find the available decoder and postprocessing elements dynamically
        if (
            parameters["object_detection_device"].startswith("GPU.")
            and int(parameters["object_detection_device"].split(".")[1]) > 0
        ):
            # Extract the GPU index (e.g., "1" from "GPU.1")
            gpu_index = parameters["object_detection_device"].split(".")[1]
            # Map GPU index to the corresponding VAAPI element suffix (e.g., "129" for GPU.1)
            vaapi_suffix = str(
                128 + int(gpu_index)
            )  # 128 + 1 = 129, 128 + 2 = 130, etc.
            _decoder_element = (
                f"varenderD{vaapi_suffix}h264dec ! video/x-raw(memory:VAMemory)"
            )
            _postprocessing_element = f"varenderD{vaapi_suffix}postproc"
        else:
            # Fallback to default elements if no specific GPU is selected
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
            _postprocessing_element = next(
                ("vapostproc" for element in elements if element[1] == "vapostproc"),
                next(
                    (
                        "videoscale"
                        for element in elements
                        if element[1] == "videoscale"
                    ),
                    None,  # Fallback to None if no postprocessing is found
                ),
            )

        # Create the streams
        streams = ""

        # Handle inference channels
        for i in range(inference_channels):

            # Handle object detection parameters and constants
            detection_model_config = (
                f"model={constants["OBJECT_DETECTION_MODEL_PATH"]} "
                f"model-proc={constants["OBJECT_DETECTION_MODEL_PROC"]} "
            )

            if not constants["OBJECT_DETECTION_MODEL_PROC"]:
                detection_model_config = (
                    f"model={constants["OBJECT_DETECTION_MODEL_PATH"]} "
                )

            streams += self._inference_stream_decode_detect_track.format(
                **parameters,
                **constants,
                id=i,
                decoder=_decoder_element,
                detection_model_config=detection_model_config,
            )

            # Handle object classification parameters and constants
            # Do this only if the object classification model is not disabled or the device is not disabled
            if not (constants["OBJECT_CLASSIFICATION_MODEL_PATH"] == "Disabled"
                    or parameters["object_classification_device"] == "Disabled"):
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
                    id=i,
                    classification_model_config=classification_model_config,
                )

            # Overlay inference results on the inferenced video if enabled
            if parameters["pipeline_watermark_enabled"]:
                streams += "gvawatermark ! "

            streams += self._inference_stream_metadata_processing.format(
                **parameters,
                **constants,
                id=i,
            )

            # sink to compositor or fake sink depending on the compose flag
            streams += self._sink_to_compositor.format(
                **parameters,
                **constants,
                id=i,
                postprocessing=_postprocessing_element,
                max_size_buffers=0,
            )
        # Handle regular channels
        for i in range(inference_channels, channels):
            streams += self._recording_stream.format(
                **parameters,
                **constants,
                id=i,
                decoder=_decoder_element,
                postprocessing=_postprocessing_element,
            )
            # sink to compositor or fake sink depending on the compose flag
            streams += self._sink_to_compositor.format(
                **parameters,
                **constants,
                id=i,
                postprocessing=_postprocessing_element,
                max_size_buffers=1,
            )
        # Compose pipeline depending on live_preview_enabled
        if parameters["live_preview_enabled"]:
            # Calculate output video size for grid layout to ensure same resolution for shmsink and output file
            output_width = 640 * grid_size
            output_height = 360 * ((channels + grid_size - 1) // grid_size)  # ceil(channels / grid_size)

            # Always produce both file and live stream outputs
            try:
                os.makedirs("/tmp/shared_memory", exist_ok=True)
                with open(VIDEO_STREAM_META_PATH, "wb") as f:
                    # width=output_height, height=output_width, dtype_size=UINT8_DTYPE_SIZE (uint8)
                    f.write(struct.pack("III", output_height, output_width, UINT8_DTYPE_SIZE))
            except Exception as e:
                logging.warning(f"Could not write shared memory meta file: {e}")

            streams = self._compositor_with_tee.format(
                **constants,
                sinks=sinks,
                encoder=_encoder_element,
                compositor=_compositor_element,
                shmsink=self._shmsink,
                output_width=output_width,
                output_height=output_height,
            ) + streams
        else:
            # Prepend the compositor
            streams = self._compositor.format(
                **constants,
                sinks=sinks,
                encoder=_encoder_element,
                compositor=_compositor_element,
            ) + streams

        # Evaluate the pipeline
        return "gst-launch-1.0 -q " + streams
