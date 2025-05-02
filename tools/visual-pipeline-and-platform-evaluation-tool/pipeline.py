import math
from pathlib import Path
from typing import List


class GstPipeline:
    def __init__(self):
        pass

    def pipeline(self) -> str:
        if not hasattr(self, "_pipeline"):
            raise ValueError("Pipeline is not defined")

        return self._pipeline

    def evaluate(
        self,
        constants: dict,
        parameters: dict,
        regular_channels: int,
        inference_channels,
    ) -> str:
        raise NotImplementedError(
            "The evaluate method must be implemented by subclasses"
        )

    def diagram(self) -> Path:
        if not hasattr(self, "_diagram"):
            raise ValueError("Diagram is not defined")

        return self._diagram

    def bounding_boxes(self) -> List:
        if not hasattr(self, "_bounding_boxes"):
            raise ValueError("Bounding Boxes is not defined")

        return self._bounding_boxes


class Transportation2Pipeline(GstPipeline):
    def __init__(self):
        super().__init__()

        self._diagram = Path("diagrams/transportation2.drawio.png")

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


class SmartNVRPipeline(GstPipeline):
    def __init__(self):
        super().__init__()

        self._diagram = Path("diagrams/smartnvr.drawio.png")

        self._bounding_boxes = [
            (325, 108, 445, 168, "Inference", "Object Detection"),
        ]

        self._sink = (
            "sink_{id}::xpos={xpos} " "sink_{id}::ypos={ypos} " "sink_{id}::alpha=1 "
        )

        self._compositor = (
            "{compositor} "
            "  name=comp "
            "  {sinks} ! "
            "{encoder} ! "
            "h264parse ! "
            "mp4mux ! "
            "filesink "
            "  location={VIDEO_OUTPUT_PATH} "
        )

        self._recording_stream = (
            "filesrc "
            "  location={VIDEO_PATH} ! "
            "qtdemux ! "
            "h264parse ! "
            "tee name=t{id} ! "
            "queue2 max-size-bytes=0 max-size-time=0 ! "
            "mp4mux ! "
            "filesink "
            "  location=/tmp/stream{id}.mp4 "
            "t{id}. ! "
            "queue2 max-size-bytes=0 max-size-time=0 ! "
            "{decoder} ! "
            "gvafpscounter starting-frame=1000 ! "
            "queue2 max-size-bytes=0 max-size-time=0 ! "
            "{postprocessing} ! "
            "video/x-raw,width=640,height=360 ! "
            "comp.sink_{id} "
        )

        self._inference_stream = (
            "filesrc "
            "  location={VIDEO_PATH} ! "
            "qtdemux ! "
            "h264parse ! "
            "tee name=t{id} ! "
            "queue2 max-size-bytes=0 max-size-time=0 ! "
            "mp4mux ! "
            "filesink "
            "  location=/tmp/stream{id}.mp4 "
            "t{id}. ! "
            "queue2 max-size-bytes=0 max-size-time=0 ! "
            "{decoder} ! "
            "gvafpscounter starting-frame=1000 ! "
            "gvadetect "
            "  model={OBJECT_DETECTION_MODEL_PATH} "
            "  model-proc={OBJECT_DETECTION_MODEL_PROC} "
            "  inference-interval=3 "
            "  model-instance-id=detect0 "
            "  pre-process-backend={object_detection_pre_process_backend} "
            "  device={object_detection_device} ! "
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
            "gvawatermark ! "
            "gvametaconvert "
            "  format=json "
            "  json-indent=4 "
            "  source={VIDEO_PATH} ! "
            "gvametapublish "
            "  method=file "
            "  file-path=/dev/null ! "
            "queue2 max-size-bytes=0 max-size-time=0 ! "
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
        elements: List[ tuple[str, str, str] ] = [],
    ) -> str:

        parameters["object_detection_pre_process_backend"] = (
            "opencv"
            if parameters["object_detection_device"] in ["CPU", "NPU"] 
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

        # Find the available compositor in elements
        _compositor_element = next(
            ("vacompositor" for element in elements if element[1] == "vacompositor"),
            next(
                ("compositor" for element in elements if element[1] == "compositor"),
                None  # Fallback to None if no compositor is found
            )
        )

        # Find the available encoder in elements
        _encoder_element = next(
            ("vah264lpenc" for element in elements if element[1] == "vah264lpenc"),
            next(
                ("vah264enc" for element in elements if element[1] == "vah264enc"),
                next(
                    ("x264enc bitrate=16000 speed-preset=superfast" for element in elements if element[1] == "x264enc"),
                    None  # Fallback to None if no encoder is found
                )
            )
        )

        # Find the available decoder in elements
        _decoder_element = next(
            ("vah264dec ! video/x-raw(memory:VAMemory) " for element in elements if element[1] == "vah264dec"),
            next(
                ("decodebin" for element in elements if element[1] == "decodebin"),
                None  # Fallback to None if no decoder is found
            )
        )

        # Find the postprocessing element
        _postprocessing_element = next(
            ("vapostproc" for element in elements if element[1] == "vapostproc"),
            next(
                ("videoscale" for element in elements if element[1] == "videoscale"),
                None  # Fallback to None if no postprocessing is found
            )
        )

        # Create the compositor
        compositor = self._compositor.format(
            **constants, 
            sinks=sinks, 
            encoder=_encoder_element, 
            compositor=_compositor_element)

        # Create the streams
        streams = ""

        for i in range(inference_channels):
            streams += self._inference_stream.format(
                **parameters,
                **constants,
                id=i,
                decoder=_decoder_element,
                postprocessing=_postprocessing_element
            )

        for i in range(inference_channels, channels):
            streams += self._recording_stream.format(
                **parameters, 
                **constants, 
                id=i, 
                decoder=_decoder_element,
                postprocessing=_postprocessing_element
            )


        # Evaluate the pipeline
        return "gst-launch-1.0 -q " + compositor + " " + streams


# Example usage
if __name__ == "__main__":
    pipeline = SmartNVRPipeline()
    print("Diagram Path:", pipeline.diagram())
    print("Bounding Boxes:", pipeline.bounding_boxes())
    print("Pipeline:", pipeline.pipeline())
    print(
        "Evaluate:",
        pipeline.evaluate(
            {
                "VIDEO_OUTPUT_PATH": "output.mp4",
                "VIDEO_PATH": "input.mp4",
                "OBJECT_DETECTION_MODEL_PATH": "model.xml",
                "OBJECT_DETECTION_MODEL_PROC": "model_proc.xml",
            },
            {"object_detection_device": "CPU"},
            2,
        ),
    )