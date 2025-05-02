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
            "vacompositor "
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
            "queue2 ! "
            "mp4mux ! "
            "filesink "
            "  location=/tmp/stream{id}.mp4 "
            "t{id}. ! "
            "queue2 ! "
            "vah264dec ! "
            "video/x-raw(memory:VAMemory) ! "
            "gvafpscounter "
            "  starting-frame=1000 ! "
            "queue2 ! "
            "vapostproc ! "
            "video/x-raw,width=640,height=360 ! "
            "comp.sink_{id} "
        )

        self._decode = (
            "vah264dec ! "
            "video/x-raw(memory:VAMemory) ! "
        )

        self._gpscounter = (
            "gvafpscounter "
            "  starting-frame=1000 ! "
        )

        self._detection = (
            "gvadetect "
            "  model={OBJECT_DETECTION_MODEL_PATH} "
            "  model-proc={OBJECT_DETECTION_MODEL_PROC} "
            "  model-instance-id=detect0 "
            "  pre-process-backend={object_detection_pre_process_backend} "
            "  device={object_detection_device} "
            "  bitrate={batch_size} "  # Add batch size as bitrate
            "  inference-interval={inference_interval} " 
            "  nireq={nireq} ! "  # Add nireq
            "queue2 "
            "  max-size-buffers=0 "
            "  max-size-bytes=0 "
            "  max-size-time=0 ! "
        )

        self._watermark = (
            "gvawatermark ! "
        )

        self._metadata = (
            "gvametaconvert "
            "  format=json "
            "  json-indent=4 "
            "  source={VIDEO_PATH} ! "
            "gvametapublish "
            "  method=file "
            "  file-path=/dev/null ! "
        )

        self._storage = (
            "mp4mux ! "
            "filesink "
            "  location=/tmp/stream{id}.mp4 "
        )


    def build_inference_stream(self, constants:dict):

        self._inference_stream = (
            "filesrc "
            "  location={VIDEO_PATH} ! "
            "qtdemux ! "
            "h264parse ! "
            "tee name=t{id} ! "
            "queue2 ! "
            + " " + self._storage + " "
            "t{id}. ! "
            "queue2 ! "
            + " " 
            + self._decode
            + self._gpscounter
            + self._detection
            + self._watermark
            + self._metadata
            + " "
            "queue2 ! "
            "vapostproc ! "
            "video/x-raw,width=640,height=360 ! "
            "comp.sink_{id} "
        )
    
    def evaluate(
        self,
        constants: dict,
        parameters: dict,
        regular_channels: int,
        inference_channels: int,
        encoder: str,
    ) -> str:

        parameters["object_detection_pre_process_backend"] = (
            "opencv"
            if parameters["object_detection_device"] in ["CPU", "NPU"] 
            else "va-surface-sharing"
        )

        self.build_inference_stream(constants)

        # Compute total number of channels
        channels = regular_channels + inference_channels

        # Create a sink for each channel
        sinks = ""
        grid_size = math.ceil(math.sqrt(channels))
        for i in range(channels):
            xpos = 640 * (i % grid_size)
            ypos = 360 * (i // grid_size)
            sinks += self._sink.format(id=i, xpos=xpos, ypos=ypos)

        # Create the compositor
        compositor = self._compositor.format(**constants, sinks=sinks, encoder=encoder)

        # Create the streams
        streams = ""

        for i in range(inference_channels):
            streams += self._inference_stream.format(**parameters, **constants, id=i)

        for i in range(inference_channels, channels):
            streams += self._recording_stream.format(**parameters, **constants, id=i)

        # Print the pipeline string
        print("Generated Pipeline String:", "gst-launch-1.0 -q " + compositor + " " + streams)
        # Evaluate the pipeline
        return "gst-launch-1.0 -q " + compositor + " " + streams


# Example usage
if __name__ == "__main__":
    pipeline = SmartNVRPipeline()
    print("Diagram Path:", pipeline.diagram())
    print("Bounding Boxes:", pipeline.bounding_boxes())
    # print("Pipeline:", pipeline.pipeline())
    print(
        "Evaluate:",
        pipeline.evaluate(
            {
                "VIDEO_OUTPUT_PATH": "output.mp4",
                "VIDEO_PATH": "input.mp4",
                "OBJECT_DETECTION_MODEL_PATH": "model.xml",
                "OBJECT_DETECTION_MODEL_PROC": "model_proc.xml",
            },
            {"object_detection_device": "CPU",
             "batch_size": 16,  # Add batch size
             "inference_interval": 2,  # Add inference interval
             "nireq": 4,  # Add nireq
             },
            2,
            1,
            "x264enc"
        ),
    )