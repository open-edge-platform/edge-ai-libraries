import re
import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from graph import Graph, Node, Edge


@dataclass
class ParseTestCase:
    pipeline_description: str
    pipeline_graph: Graph


parse_test_cases = [
    # old simplevs
    ParseTestCase(
        r"filesrc location=/tmp/license-plate-detection.mp4 ! decodebin3 ! vapostproc ! "
        r"video/x-raw(memory:VAMemory) ! gvafpscounter starting-frame=500 ! "
        r"gvadetect model=/yolov8_license_plate_detector.xml model-instance-id=detect0 device=GPU "
        r"pre-process-backend=va-surface-sharing batch-size=0 inference-interval=3 nireq=0 ! queue ! "
        r"gvatrack tracking-type=short-term-imageless ! queue ! "
        r"gvaclassify model=/ch_PP-OCRv4_rec_infer/ch_PP-OCRv4_rec_infer.xml "
        r"model-instance-id=classify0 device=GPU pre-process-backend=va-surface-sharing batch-size=0 "
        r"inference-interval=3 nireq=0 reclassify-interval=1 ! queue ! gvawatermark ! "
        r"gvametaconvert format=json json-indent=4 source=/tmp/license-plate-detection.mp4 ! "
        r"gvametapublish method=file file-path=/dev/null ! vah264enc ! h264parse ! mp4mux ! "
        r"filesink location=/tmp/license-plate-detection-output.mp4",
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "/tmp/license-plate-detection.mp4"},
                ),
                Node(id="1", type="decodebin3", data={}),
                Node(id="2", type="vapostproc", data={}),
                Node(id="3", type="video/x-raw(memory:VAMemory)", data={}),
                Node(id="4", type="gvafpscounter", data={"starting-frame": "500"}),
                Node(
                    id="5",
                    type="gvadetect",
                    data={
                        "model": "/yolov8_license_plate_detector.xml",
                        "model-instance-id": "detect0",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "batch-size": "0",
                        "inference-interval": "3",
                        "nireq": "0",
                    },
                ),
                Node(id="6", type="queue", data={}),
                Node(
                    id="7",
                    type="gvatrack",
                    data={"tracking-type": "short-term-imageless"},
                ),
                Node(id="8", type="queue", data={}),
                Node(
                    id="9",
                    type="gvaclassify",
                    data={
                        "model": "/ch_PP-OCRv4_rec_infer/ch_PP-OCRv4_rec_infer.xml",
                        "model-instance-id": "classify0",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "batch-size": "0",
                        "inference-interval": "3",
                        "nireq": "0",
                        "reclassify-interval": "1",
                    },
                ),
                Node(id="10", type="queue", data={}),
                Node(id="11", type="gvawatermark", data={}),
                Node(
                    id="12",
                    type="gvametaconvert",
                    data={
                        "format": "json",
                        "json-indent": "4",
                        "source": "/tmp/license-plate-detection.mp4",
                    },
                ),
                Node(
                    id="13",
                    type="gvametapublish",
                    data={"method": "file", "file-path": "/dev/null"},
                ),
                Node(id="14", type="vah264enc", data={}),
                Node(id="15", type="h264parse", data={}),
                Node(id="16", type="mp4mux", data={}),
                Node(
                    id="17",
                    type="filesink",
                    data={"location": "/tmp/license-plate-detection-output.mp4"},
                ),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
                Edge(id="12", source="12", target="13"),
                Edge(id="13", source="13", target="14"),
                Edge(id="14", source="14", target="15"),
                Edge(id="15", source="15", target="16"),
                Edge(id="16", source="16", target="17"),
            ],
        ),
    ),
    # gst docs tee example
    ParseTestCase(
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
        r"! autoaudiosink t. ! queue ! audioconvert ! goom ! videoconvert ! autovideosink",
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "song.ogg"},
                ),
                Node(id="1", type="decodebin", data={}),
                Node(id="2", type="tee", data={"name": "t"}),
                Node(id="3", type="queue", data={}),
                Node(id="4", type="audioconvert", data={}),
                Node(id="5", type="audioresample", data={}),
                Node(id="6", type="autoaudiosink", data={}),
                Node(id="7", type="queue", data={}),
                Node(id="8", type="audioconvert", data={}),
                Node(id="9", type="goom", data={}),
                Node(id="10", type="videoconvert", data={}),
                Node(id="11", type="autovideosink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="2", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
            ],
        ),
    ),
    # 2 nested tees
    ParseTestCase(
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! tee name=x ! "
        r"queue ! audiorate ! autoaudiosink x. ! queue ! audioresample ! autoaudiosink t. ! queue "
        r"! audioconvert ! goom ! videoconvert ! autovideosink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "song.ogg"}),
                Node(id="1", type="decodebin", data={}),
                Node(id="2", type="tee", data={"name": "t"}),
                Node(id="3", type="queue", data={}),
                Node(id="4", type="audioconvert", data={}),
                Node(id="5", type="tee", data={"name": "x"}),
                Node(id="6", type="queue", data={}),
                Node(id="7", type="audiorate", data={}),
                Node(id="8", type="autoaudiosink", data={}),
                Node(id="9", type="queue", data={}),
                Node(id="10", type="audioresample", data={}),
                Node(id="11", type="autoaudiosink", data={}),
                Node(id="12", type="queue", data={}),
                Node(id="13", type="audioconvert", data={}),
                Node(id="14", type="goom", data={}),
                Node(id="15", type="videoconvert", data={}),
                Node(id="16", type="autovideosink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="5", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="2", target="12"),
                Edge(id="12", source="12", target="13"),
                Edge(id="13", source="13", target="14"),
                Edge(id="14", source="14", target="15"),
                Edge(id="15", source="15", target="16"),
            ],
        ),
    ),
    # template
    ParseTestCase(
        r"filesrc location=XXX ! demux ! tee name=t ! queue ! splitmuxsink location=output_%02d.mp4 "
        r"t. ! queue ! h264parse ! vah264dec ! "
        r"gvadetect ! queue ! gvatrack ! gvaclassify ! queue ! "
        r"gvawatermark ! gvafpscounter ! gvametaconvert ! gvametapublish ! "
        r"vah264enc ! h264parse ! mp4mux ! filesink location=YYY",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "XXX"}),
                Node(id="1", type="demux", data={}),
                Node(id="2", type="tee", data={"name": "t"}),
                Node(id="3", type="queue", data={}),
                Node(
                    id="4",
                    type="splitmuxsink",
                    data={"location": "output_%02d.mp4"},
                ),
                Node(id="5", type="queue", data={}),
                Node(id="6", type="h264parse", data={}),
                Node(id="7", type="vah264dec", data={}),
                Node(id="8", type="gvadetect", data={}),
                Node(id="9", type="queue", data={}),
                Node(id="10", type="gvatrack", data={}),
                Node(id="11", type="gvaclassify", data={}),
                Node(id="12", type="queue", data={}),
                Node(id="13", type="gvawatermark", data={}),
                Node(id="14", type="gvafpscounter", data={}),
                Node(id="15", type="gvametaconvert", data={}),
                Node(id="16", type="gvametapublish", data={}),
                Node(id="17", type="vah264enc", data={}),
                Node(id="18", type="h264parse", data={}),
                Node(id="19", type="mp4mux", data={}),
                Node(id="20", type="filesink", data={"location": "YYY"}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="2", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
                Edge(id="12", source="12", target="13"),
                Edge(id="13", source="13", target="14"),
                Edge(id="14", source="14", target="15"),
                Edge(id="15", source="15", target="16"),
                Edge(id="16", source="16", target="17"),
                Edge(id="17", source="17", target="18"),
                Edge(id="18", source="18", target="19"),
                Edge(id="19", source="19", target="20"),
            ],
        ),
    ),
    # SmartNVR Analytics Branch
    ParseTestCase(
        r"filesrc location=${VIDEO} ! qtdemux ! h264parse ! "
        r"tee name=t0 ! queue2 ! splitmuxsink location=/tmp/$(uuid).mp4 "
        r"t0. ! queue2 ! vah264dec ! video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"gvadetect   model=${MODEL_YOLOv5s_416} model-proc=${MODEL_PROC_YOLOv5s_416} "
        r"model-instance-id=detect0   pre-process-backend=va-surface-sharing device=GPU "
        r"batch-size=0 inference-interval=3 nireq=0 ! queue2 ! "
        r"gvatrack tracking-type=short-term-imageless ! queue2 ! "
        r"gvaclassify   model=${MODEL_RESNET} model-proc=${MODEL_PROC_RESNET} "
        r"model-instance-id=classify0 pre-process-backend=va-surface-sharing device=GPU "
        r"batch-size=0 inference-interval=3 nireq=0 reclassify-interval=1 ! queue2 ! "
        r"gvawatermark ! "
        r"gvametaconvert format=json json-indent=4 ! "
        r"gvametapublish method=file file-path=/dev/null ! "
        r"vapostproc ! video/x-raw\(memory:VAMemory\),width=320,height=240 ! fakesink",
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="h264parse", data={}),
                Node(id="3", type="tee", data={"name": "t0"}),
                Node(id="4", type="queue2", data={}),
                Node(
                    id="5",
                    type="splitmuxsink",
                    data={"location": "/tmp/$(uuid).mp4"},
                ),
                Node(id="6", type="queue2", data={}),
                Node(id="7", type="vah264dec", data={}),
                Node(
                    id="8",
                    type="video/x-raw\\(memory:VAMemory\\)",
                    data={},
                ),
                Node(
                    id="9",
                    type="gvafpscounter",
                    data={"starting-frame": "500"},
                ),
                Node(
                    id="10",
                    type="gvadetect",
                    data={
                        "model": "${MODEL_YOLOv5s_416}",
                        "model-proc": "${MODEL_PROC_YOLOv5s_416}",
                        "model-instance-id": "detect0",
                        "pre-process-backend": "va-surface-sharing",
                        "device": "GPU",
                        "batch-size": "0",
                        "inference-interval": "3",
                        "nireq": "0",
                    },
                ),
                Node(id="11", type="queue2", data={}),
                Node(
                    id="12",
                    type="gvatrack",
                    data={"tracking-type": "short-term-imageless"},
                ),
                Node(id="13", type="queue2", data={}),
                Node(
                    id="14",
                    type="gvaclassify",
                    data={
                        "model": "${MODEL_RESNET}",
                        "model-proc": "${MODEL_PROC_RESNET}",
                        "model-instance-id": "classify0",
                        "pre-process-backend": "va-surface-sharing",
                        "device": "GPU",
                        "batch-size": "0",
                        "inference-interval": "3",
                        "nireq": "0",
                        "reclassify-interval": "1",
                    },
                ),
                Node(id="15", type="queue2", data={}),
                Node(id="16", type="gvawatermark", data={}),
                Node(
                    id="17",
                    type="gvametaconvert",
                    data={"format": "json", "json-indent": "4"},
                ),
                Node(
                    id="18",
                    type="gvametapublish",
                    data={"method": "file", "file-path": "/dev/null"},
                ),
                Node(id="19", type="vapostproc", data={}),
                Node(
                    id="20",
                    type="video/x-raw\\(memory:VAMemory\\)",
                    data={"width": "320", "height": "240"},
                ),
                Node(id="21", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="3", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
                Edge(id="12", source="12", target="13"),
                Edge(id="13", source="13", target="14"),
                Edge(id="14", source="14", target="15"),
                Edge(id="15", source="15", target="16"),
                Edge(id="16", source="16", target="17"),
                Edge(id="17", source="17", target="18"),
                Edge(id="18", source="18", target="19"),
                Edge(id="19", source="19", target="20"),
                Edge(id="20", source="20", target="21"),
            ],
        ),
    ),
    # SmartNVR Media-only Branch
    ParseTestCase(
        r"filesrc location=${VIDEO} ! qtdemux ! h264parse ! "
        r"tee name=t0 ! queue2 ! splitmuxsink location=/tmp/$(uuid).mp4 "
        r"t0. ! queue2 ! vah264dec ! video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"vapostproc ! video/x-raw\(memory:VAMemory\),width=320,height=240 ! fakesink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="h264parse", data={}),
                Node(id="3", type="tee", data={"name": "t0"}),
                Node(id="4", type="queue2", data={}),
                Node(
                    id="5",
                    type="splitmuxsink",
                    data={"location": "/tmp/$(uuid).mp4"},
                ),
                Node(id="6", type="queue2", data={}),
                Node(id="7", type="vah264dec", data={}),
                Node(id="8", type="video/x-raw\\(memory:VAMemory\\)", data={}),
                Node(id="9", type="gvafpscounter", data={"starting-frame": "500"}),
                Node(id="10", type="vapostproc", data={}),
                Node(
                    id="11",
                    type="video/x-raw\\(memory:VAMemory\\)",
                    data={"width": "320", "height": "240"},
                ),
                Node(id="12", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="3", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
            ],
        ),
    ),
    # Magic 9 Light
    ParseTestCase(
        r"filesrc location=${VIDEO} ! h265parse ! vah265dec ! "
        r"capsfilter caps=\"video/x-raw(memory:VAMemory)\" ! queue ! "
        r"gvadetect model=${MODEL_YOLOv11n} model-proc=${MODEL_PROC_YOLOv11n} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 threshold=0.5 model-instance-id=yolov11n ! "
        r"queue ! "
        r"gvatrack tracking-type=1 config=tracking_per_class=false ! queue ! "
        r"gvaclassify model=${MODEL_RESNET} model-proc=${MODEL_PROC_RESNET} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 inference-region=1 "
        r"model-instance-id=resnet50 ! queue ! "
        r"gvafpscounter starting-frame=2000 ! fakesink sync=false async=false",
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
                Node(id="1", type="h265parse", data={}),
                Node(id="2", type="vah265dec", data={}),
                Node(
                    id="3",
                    type="capsfilter",
                    data={"caps": '\\"video/x-raw(memory:VAMemory)\\"'},
                ),
                Node(id="4", type="queue", data={}),
                Node(
                    id="5",
                    type="gvadetect",
                    data={
                        "model": "${MODEL_YOLOv11n}",
                        "model-proc": "${MODEL_PROC_YOLOv11n}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "nireq": "2",
                        "ie-config": "NUM_STREAMS=2",
                        "batch-size": "8",
                        "inference-interval": "3",
                        "threshold": "0.5",
                        "model-instance-id": "yolov11n",
                    },
                ),
                Node(id="6", type="queue", data={}),
                Node(
                    id="7",
                    type="gvatrack",
                    data={
                        "tracking-type": "1",
                        "config": "tracking_per_class=false",
                    },
                ),
                Node(id="8", type="queue", data={}),
                Node(
                    id="9",
                    type="gvaclassify",
                    data={
                        "model": "${MODEL_RESNET}",
                        "model-proc": "${MODEL_PROC_RESNET}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "nireq": "2",
                        "ie-config": "NUM_STREAMS=2",
                        "batch-size": "8",
                        "inference-interval": "3",
                        "inference-region": "1",
                        "model-instance-id": "resnet50",
                    },
                ),
                Node(id="10", type="queue", data={}),
                Node(
                    id="11",
                    type="gvafpscounter",
                    data={"starting-frame": "2000"},
                ),
                Node(
                    id="12",
                    type="fakesink",
                    data={"sync": "false", "async": "false"},
                ),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
            ],
        ),
    ),
    # Magic 9 Medium
    ParseTestCase(
        r"filesrc location=${VIDEO} ! h265parse ! vah265dec ! "
        r"capsfilter caps=\"video/x-raw(memory:VAMemory)\" ! queue ! "
        r"gvadetect model=${MODEL_YOLOv5m} model-proc=${MODEL_PROC_YOLOv5m} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 threshold=0.5 model-instance-id=yolov5m ! "
        r"queue ! "
        r"gvatrack tracking-type=1 config=tracking_per_class=false ! queue ! "
        r"gvaclassify model=${MODEL_RESNET} model-proc=${MODEL_PROC_RESNET} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 inference-region=1 "
        r"model-instance-id=resnet50 ! queue ! "
        r"gvaclassify model=${MODEL_MOBILENET} model-proc=${MODEL_PROC_MOBILENET} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 inference-region=1 "
        r"model-instance-id=mobilenetv2 ! queue ! "
        r"gvafpscounter starting-frame=2000 ! fakesink sync=false async=false",
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
                Node(id="1", type="h265parse", data={}),
                Node(id="2", type="vah265dec", data={}),
                Node(
                    id="3",
                    type="capsfilter",
                    data={"caps": '\\"video/x-raw(memory:VAMemory)\\"'},
                ),
                Node(id="4", type="queue", data={}),
                Node(
                    id="5",
                    type="gvadetect",
                    data={
                        "model": "${MODEL_YOLOv5m}",
                        "model-proc": "${MODEL_PROC_YOLOv5m}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "nireq": "2",
                        "ie-config": "NUM_STREAMS=2",
                        "batch-size": "8",
                        "inference-interval": "3",
                        "threshold": "0.5",
                        "model-instance-id": "yolov5m",
                    },
                ),
                Node(id="6", type="queue", data={}),
                Node(
                    id="7",
                    type="gvatrack",
                    data={
                        "tracking-type": "1",
                        "config": "tracking_per_class=false",
                    },
                ),
                Node(id="8", type="queue", data={}),
                Node(
                    id="9",
                    type="gvaclassify",
                    data={
                        "model": "${MODEL_RESNET}",
                        "model-proc": "${MODEL_PROC_RESNET}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "nireq": "2",
                        "ie-config": "NUM_STREAMS=2",
                        "batch-size": "8",
                        "inference-interval": "3",
                        "inference-region": "1",
                        "model-instance-id": "resnet50",
                    },
                ),
                Node(id="10", type="queue", data={}),
                Node(
                    id="11",
                    type="gvaclassify",
                    data={
                        "model": "${MODEL_MOBILENET}",
                        "model-proc": "${MODEL_PROC_MOBILENET}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "nireq": "2",
                        "ie-config": "NUM_STREAMS=2",
                        "batch-size": "8",
                        "inference-interval": "3",
                        "inference-region": "1",
                        "model-instance-id": "mobilenetv2",
                    },
                ),
                Node(id="12", type="queue", data={}),
                Node(
                    id="13",
                    type="gvafpscounter",
                    data={"starting-frame": "2000"},
                ),
                Node(
                    id="14",
                    type="fakesink",
                    data={"sync": "false", "async": "false"},
                ),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
                Edge(id="12", source="12", target="13"),
                Edge(id="13", source="13", target="14"),
            ],
        ),
    ),
    # Magic 9 Heavy
    ParseTestCase(
        r"filesrc location=${VIDEO}! h265parse ! vah265dec ! "
        r"capsfilter caps=\"video/x-raw(memory:VAMemory)\" ! queue ! "
        r"gvadetect model=${MODEL_YOLOv11n} model-proc=${MODEL_PROC_YOLOv11n} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 threshold=0.5 model-instance-id=yolov11m ! "
        r"queue ! "
        r"gvatrack tracking-type=1 config=tracking_per_class=false ! queue ! "
        r"gvaclassify model=${MODEL_RESNET} model-proc=${MODEL_PROC_RESNET} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 inference-region=1 "
        r"model-instance-id=resnet50 ! queue ! "
        r"gvaclassify model=${MODEL_MOBILENET} model-proc=${MODEL_PROC_MOBILENET} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 inference-region=1 "
        r"model-instance-id=mobilenetv2 ! queue ! "
        r"gvafpscounter starting-frame=2000 ! fakesink sync=false async=false",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
                Node(id="1", type="h265parse", data={}),
                Node(id="2", type="vah265dec", data={}),
                Node(
                    id="3",
                    type="capsfilter",
                    data={"caps": '\\"video/x-raw(memory:VAMemory)\\"'},
                ),
                Node(id="4", type="queue", data={}),
                Node(
                    id="5",
                    type="gvadetect",
                    data={
                        "model": "${MODEL_YOLOv11n}",
                        "model-proc": "${MODEL_PROC_YOLOv11n}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "nireq": "2",
                        "ie-config": "NUM_STREAMS=2",
                        "batch-size": "8",
                        "inference-interval": "3",
                        "threshold": "0.5",
                        "model-instance-id": "yolov11m",
                    },
                ),
                Node(id="6", type="queue", data={}),
                Node(
                    id="7",
                    type="gvatrack",
                    data={
                        "tracking-type": "1",
                        "config": "tracking_per_class=false",
                    },
                ),
                Node(id="8", type="queue", data={}),
                Node(
                    id="9",
                    type="gvaclassify",
                    data={
                        "model": "${MODEL_RESNET}",
                        "model-proc": "${MODEL_PROC_RESNET}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "nireq": "2",
                        "ie-config": "NUM_STREAMS=2",
                        "batch-size": "8",
                        "inference-interval": "3",
                        "inference-region": "1",
                        "model-instance-id": "resnet50",
                    },
                ),
                Node(id="10", type="queue", data={}),
                Node(
                    id="11",
                    type="gvaclassify",
                    data={
                        "model": "${MODEL_MOBILENET}",
                        "model-proc": "${MODEL_PROC_MOBILENET}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "nireq": "2",
                        "ie-config": "NUM_STREAMS=2",
                        "batch-size": "8",
                        "inference-interval": "3",
                        "inference-region": "1",
                        "model-instance-id": "mobilenetv2",
                    },
                ),
                Node(id="12", type="queue", data={}),
                Node(id="13", type="gvafpscounter", data={"starting-frame": "2000"}),
                Node(
                    id="14", type="fakesink", data={"sync": "false", "async": "false"}
                ),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
                Edge(id="12", source="12", target="13"),
                Edge(id="13", source="13", target="14"),
            ],
        ),
    ),
    # Simple Video Structuration
    ParseTestCase(
        r"filesrc location=${VIDEO} ! qtdemux ! h264parse ! vaapidecodebin ! "
        r"vapostproc ! video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"gvadetect   model=${LPR_MODEL} model-instance-id=detect0 "
        r"pre-process-backend=va-surface-sharing   device=GPU   batch-size=0   inference-interval=3  nireq=0 ! "
        r"queue2 ! gvatrack   tracking-type=short-term-imageless ! queue2 ! "
        r"gvaclassify   model=${OCR_MODEL} model-instance-id=classify0 "
        r"pre-process-backend=va-surface-sharing   device=GPU   batch-size=0   inference-interval=3   nireq=0 "
        r"reclassify-interval=1 ! queue2 ! gvawatermark ! gvametaconvert   format=json   json-indent=4 ! "
        r"gvametapublish   method=file file-path=/dev/null ! "
        r"fakesink",
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="h264parse", data={}),
                Node(id="3", type="vaapidecodebin", data={}),
                Node(id="4", type="vapostproc", data={}),
                Node(id="5", type="video/x-raw\\(memory:VAMemory\\)", data={}),
                Node(
                    id="6",
                    type="gvafpscounter",
                    data={"starting-frame": "500"},
                ),
                Node(
                    id="7",
                    type="gvadetect",
                    data={
                        "model": "${LPR_MODEL}",
                        "model-instance-id": "detect0",
                        "pre-process-backend": "va-surface-sharing",
                        "device": "GPU",
                        "batch-size": "0",
                        "inference-interval": "3",
                        "nireq": "0",
                    },
                ),
                Node(id="8", type="queue2", data={}),
                Node(
                    id="9",
                    type="gvatrack",
                    data={"tracking-type": "short-term-imageless"},
                ),
                Node(id="10", type="queue2", data={}),
                Node(
                    id="11",
                    type="gvaclassify",
                    data={
                        "model": "${OCR_MODEL}",
                        "model-instance-id": "classify0",
                        "pre-process-backend": "va-surface-sharing",
                        "device": "GPU",
                        "batch-size": "0",
                        "inference-interval": "3",
                        "nireq": "0",
                        "reclassify-interval": "1",
                    },
                ),
                Node(id="12", type="queue2", data={}),
                Node(id="13", type="gvawatermark", data={}),
                Node(
                    id="14",
                    type="gvametaconvert",
                    data={"format": "json", "json-indent": "4"},
                ),
                Node(
                    id="15",
                    type="gvametapublish",
                    data={"method": "file", "file-path": "/dev/null"},
                ),
                Node(id="16", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
                Edge(id="12", source="12", target="13"),
                Edge(id="13", source="13", target="14"),
                Edge(id="14", source="14", target="15"),
                Edge(id="15", source="15", target="16"),
            ],
        ),
    ),
    # Human Pose Pipeline
    ParseTestCase(
        r"filesrc location=${VIDEO}! qtdemux ! h264parse ! vah264dec ! "
        r"video/x-raw(memory:VAMemory) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"gvadetect model=${YOLO11n_POST_MODEL} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"model-instance-id=yolo11-pose ! queue2 ! "
        r"gvatrack tracking-type=short-term-imageless ! "
        r"gvawatermark ! gvametaconvert   format=json   json-indent=4 ! "
        r"gvametapublish   method=file file-path=/dev/null ! "
        r"fakesink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="h264parse", data={}),
                Node(id="3", type="vah264dec", data={}),
                Node(id="4", type="video/x-raw(memory:VAMemory)", data={}),
                Node(
                    id="5",
                    type="gvafpscounter",
                    data={"starting-frame": "500"},
                ),
                Node(
                    id="6",
                    type="gvadetect",
                    data={
                        "model": "${YOLO11n_POST_MODEL}",
                        "device": "GPU",
                        "pre-process-backend": "va-surface-sharing",
                        "model-instance-id": "yolo11-pose",
                    },
                ),
                Node(id="7", type="queue2", data={}),
                Node(
                    id="8",
                    type="gvatrack",
                    data={"tracking-type": "short-term-imageless"},
                ),
                Node(id="9", type="gvawatermark", data={}),
                Node(
                    id="10",
                    type="gvametaconvert",
                    data={"format": "json", "json-indent": "4"},
                ),
                Node(
                    id="11",
                    type="gvametapublish",
                    data={"method": "file", "file-path": "/dev/null"},
                ),
                Node(id="12", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="11", source="11", target="12"),
            ],
        ),
    ),
    # Video Decode Pipeline
    ParseTestCase(
        r"filesrc location=${VIDEO} ! qtdemux ! h264parse ! vah264dec ! "
        r"video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"fakesink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="h264parse", data={}),
                Node(id="3", type="vah264dec", data={}),
                Node(
                    id="4",
                    type="video/x-raw\\(memory:VAMemory\\)",
                    data={},
                ),
                Node(
                    id="5",
                    type="gvafpscounter",
                    data={"starting-frame": "500"},
                ),
                Node(id="6", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
            ],
        ),
    ),
    # Video Decode Scale Pipeline
    ParseTestCase(
        r"filesrc location=${VIDEO} ! qtdemux ! h264parse ! vah264dec ! "
        r"video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"vapostproc ! video/x-raw\(memory:VAMemory\),width=320,height=240 ! fakesink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="h264parse", data={}),
                Node(id="3", type="vah264dec", data={}),
                Node(id="4", type="video/x-raw\\(memory:VAMemory\\)", data={}),
                Node(id="5", type="gvafpscounter", data={"starting-frame": "500"}),
                Node(id="6", type="vapostproc", data={}),
                Node(
                    id="7",
                    type="video/x-raw\\(memory:VAMemory\\)",
                    data={"width": "320", "height": "240"},
                ),
                Node(id="8", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
            ],
        ),
    ),
]


unsorted_nodes_edges = [
    # gst docs tee example
    ParseTestCase(
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
        r"! autoaudiosink t. ! queue ! audioconvert ! goom ! videoconvert ! autovideosink",
        Graph(
            nodes=[
                Node(id="1", type="decodebin", data={}),
                Node(id="0", type="filesrc", data={"location": "song.ogg"}),
                Node(id="3", type="queue", data={}),
                Node(id="6", type="autoaudiosink", data={}),
                Node(id="4", type="audioconvert", data={}),
                Node(id="8", type="audioconvert", data={}),
                Node(id="5", type="audioresample", data={}),
                Node(id="7", type="queue", data={}),
                Node(id="11", type="autovideosink", data={}),
                Node(id="9", type="goom", data={}),
                Node(id="2", type="tee", data={"name": "t"}),
                Node(id="10", type="videoconvert", data={}),
            ],
            edges=[
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="0", source="0", target="1"),
                Edge(id="7", source="7", target="8"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="10", source="10", target="11"),
                Edge(id="6", source="2", target="7"),
                Edge(id="9", source="9", target="10"),
                Edge(id="8", source="8", target="9"),
            ],
        ),
    ),
    # gst docs tee example, ids start from 1
    ParseTestCase(
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
        r"! autoaudiosink t. ! queue ! audioconvert ! goom ! videoconvert ! autovideosink",
        Graph(
            nodes=[
                Node(id="2", type="decodebin", data={}),
                Node(id="1", type="filesrc", data={"location": "song.ogg"}),
                Node(id="4", type="queue", data={}),
                Node(id="7", type="autoaudiosink", data={}),
                Node(id="5", type="audioconvert", data={}),
                Node(id="9", type="audioconvert", data={}),
                Node(id="6", type="audioresample", data={}),
                Node(id="8", type="queue", data={}),
                Node(id="12", type="autovideosink", data={}),
                Node(id="10", type="goom", data={}),
                Node(id="3", type="tee", data={"name": "t"}),
                Node(id="11", type="videoconvert", data={}),
            ],
            edges=[
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="1", source="1", target="2"),
                Edge(id="8", source="8", target="9"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="11", source="11", target="12"),
                Edge(id="7", source="3", target="8"),
                Edge(id="10", source="10", target="11"),
                Edge(id="9", source="9", target="10"),
            ],
        ),
    ),
    # 2 nested tees
    ParseTestCase(
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! tee name=x ! "
        r"queue ! audiorate ! autoaudiosink x. ! queue ! audioresample ! autoaudiosink t. ! queue "
        r"! audioconvert ! goom ! videoconvert ! autovideosink",
        Graph(
            nodes=[
                Node(id="1", type="decodebin", data={}),
                Node(id="3", type="queue", data={}),
                Node(id="2", type="tee", data={"name": "t"}),
                Node(id="0", type="filesrc", data={"location": "song.ogg"}),
                Node(id="4", type="audioconvert", data={}),
                Node(id="6", type="queue", data={}),
                Node(id="7", type="audiorate", data={}),
                Node(id="5", type="tee", data={"name": "x"}),
                Node(id="9", type="queue", data={}),
                Node(id="10", type="audioresample", data={}),
                Node(id="14", type="goom", data={}),
                Node(id="16", type="autovideosink", data={}),
                Node(id="8", type="autoaudiosink", data={}),
                Node(id="11", type="autoaudiosink", data={}),
                Node(id="12", type="queue", data={}),
                Node(id="13", type="audioconvert", data={}),
                Node(id="15", type="videoconvert", data={}),
            ],
            edges=[
                Edge(id="15", source="15", target="16"),
                Edge(id="1", source="1", target="2"),
                Edge(id="0", source="0", target="1"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                Edge(id="6", source="6", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="13", source="13", target="14"),
                Edge(id="8", source="5", target="9"),
                Edge(id="9", source="9", target="10"),
                Edge(id="10", source="10", target="11"),
                Edge(id="12", source="12", target="13"),
                Edge(id="11", source="2", target="12"),
                Edge(id="14", source="14", target="15"),
            ],
        ),
    ),
]


def normalize(s: str) -> str:
    s = re.sub(r" {2,}", " ", s)
    s = re.sub(r"(?<!\s)!", " !", s)
    s = re.sub(r"!(?!\s)", "! ", s)
    return s


class TestToFromDict(unittest.TestCase):
    def test_to_from_dict(self):
        self.maxDiff = None

        for tc in parse_test_cases + unsorted_nodes_edges:
            d = tc.pipeline_graph.to_dict()
            dc = Graph.from_dict(d)

            self.assertEqual(len(dc.nodes), len(tc.pipeline_graph.nodes))
            for actual, expected in zip(dc.nodes, tc.pipeline_graph.nodes):
                self.assertEqual(actual.id, expected.id)
                self.assertEqual(actual.type, expected.type)
                self.assertDictEqual(actual.data, expected.data)

            self.assertEqual(len(dc.edges), len(tc.pipeline_graph.edges))
            for actual, expected in zip(dc.edges, tc.pipeline_graph.edges):
                self.assertEqual(actual.id, expected.id)
                self.assertEqual(actual.source, expected.source)
                self.assertEqual(actual.target, expected.target)


class TestDictToString(unittest.TestCase):
    def test_dict_to_string(self):
        self.maxDiff = None

        for tc in parse_test_cases + unsorted_nodes_edges:
            actual = tc.pipeline_graph.to_pipeline_description()
            self.assertEqual(actual, normalize(tc.pipeline_description))


class TestParseLaunchString(unittest.TestCase):
    def test_parsing(self):
        self.maxDiff = None

        for tc in parse_test_cases:
            actual = Graph.from_pipeline_description(tc.pipeline_description)
            self.assertEqual(actual, tc.pipeline_graph)

    def test_empty_pipeline(self):
        pipeline = ""
        result = Graph.from_pipeline_description(pipeline)

        self.assertEqual(len(result.nodes), 0)
        self.assertEqual(len(result.edges), 0)

    def test_single_element(self):
        pipeline = "filesrc"
        result = Graph.from_pipeline_description(pipeline)

        self.assertEqual(len(result.nodes), 1)
        self.assertEqual(result.nodes[0].type, "filesrc")
        self.assertEqual(len(result.edges), 0)

    def test_caps_filter(self):
        pipeline = "filesrc ! video/x-raw(memory:VAMemory) ! filesink"
        result = Graph.from_pipeline_description(pipeline)

        self.assertEqual(len(result.nodes), 3)
        self.assertTrue(
            any(n.type == "video/x-raw(memory:VAMemory)" for n in result.nodes)
        )

    def test_node_ids_are_sequential(self):
        pipeline = "filesrc ! queue ! filesink"
        result = Graph.from_pipeline_description(pipeline)

        self.assertEqual(result.nodes[0].id, "0")
        self.assertEqual(result.nodes[1].id, "1")
        self.assertEqual(result.nodes[2].id, "2")

    def test_edge_ids_are_sequential(self):
        pipeline = "filesrc ! queue ! filesink"
        result = Graph.from_pipeline_description(pipeline)

        self.assertEqual(result.edges[0].id, "0")
        self.assertEqual(result.edges[1].id, "1")


class TestParseLaunchStringWithModels(unittest.TestCase):
    def _setup_mock_models(self, mock_manager):
        """Set up mock models for testing"""
        mock_yolov8 = MagicMock()
        mock_yolov8.display_name = "YOLOv8 Detector"
        mock_yolov8.model_path_full = "/models/output/yolov8_detector.xml"
        mock_yolov8.model_proc_full = "/models/output/yolov8_detector.json"

        mock_detection = MagicMock()
        mock_detection.display_name = "Detection Model"
        mock_detection.model_path_full = "/models/output/detection_model.xml"
        mock_detection.model_proc_full = ""

        mock_classification = MagicMock()
        mock_classification.display_name = "Classification Model"
        mock_classification.model_path_full = "/models/output/classification_model.xml"
        mock_classification.model_proc_full = ""

        def find_by_path(path):
            if "yolov8_detector" in path:
                return mock_yolov8
            if "detection_model" in path:
                return mock_detection
            if "classification_model" in path:
                return mock_classification
            return None

        def find_by_name(name):
            if name == "YOLOv8 Detector":
                return mock_yolov8
            if name == "Detection Model":
                return mock_detection
            if name == "Classification Model":
                return mock_classification
            return None

        mock_manager.find_installed_model_by_model_path_full.side_effect = find_by_path
        mock_manager.find_installed_model_by_display_name.side_effect = find_by_name

    @patch("graph.models_manager")
    def test_string_to_config_converts_model_path_to_display_name(self, mock_manager):
        self._setup_mock_models(mock_manager)

        pipeline_description = (
            "filesrc location=/tmp/input.mp4 ! decodebin3 ! gvadetect "
            "model=/models/output/yolov8_detector.xml model-proc=/models/output/yolov8_detector.json "
            "device=GPU ! fakesink"
        )

        result = Graph.from_pipeline_description(pipeline_description)

        self.assertEqual(len(result.nodes), 4)
        gvadetect_node = result.nodes[2]
        self.assertEqual(gvadetect_node.type, "gvadetect")
        self.assertEqual(gvadetect_node.data["model"], "YOLOv8 Detector")
        self.assertNotIn("model-proc", gvadetect_node.data)

    @patch("graph.models_manager")
    def test_config_to_string_converts_display_name_to_model_path(self, mock_manager):
        self._setup_mock_models(mock_manager)

        config = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "/tmp/input.mp4"}),
                Node(id="1", type="decodebin3", data={}),
                Node(
                    id="2",
                    type="gvadetect",
                    data={"model": "YOLOv8 Detector", "device": "GPU"},
                ),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )

        result = config.to_pipeline_description()

        self.assertIn("model=/models/output/yolov8_detector.xml", result)
        self.assertIn("model-proc=/models/output/yolov8_detector.json", result)
        self.assertNotIn("YOLOv8 Detector", result)

    @patch("graph.models_manager")
    def test_multiple_models_conversion(self, mock_manager):
        self._setup_mock_models(mock_manager)

        pipeline_description = (
            "filesrc location=/tmp/input.mp4 ! decodebin3 ! gvadetect "
            "model=/models/output/detection_model.xml device=GPU ! gvaclassify "
            "model=/models/output/classification_model.xml device=GPU ! fakesink"
        )

        result = Graph.from_pipeline_description(pipeline_description)

        self.assertEqual(len(result.nodes), 5)
        gvadetect_node = result.nodes[2]
        gvaclassify_node = result.nodes[3]

        self.assertEqual(gvadetect_node.data["model"], "Detection Model")
        self.assertEqual(gvaclassify_node.data["model"], "Classification Model")

        pipeline_description = result.to_pipeline_description()

        self.assertIn("model=/models/output/detection_model.xml", pipeline_description)
        self.assertIn(
            "model=/models/output/classification_model.xml", pipeline_description
        )


class TestParseLaunchStringWithVideos(unittest.TestCase):
    def _setup_mock_videos(self, mock_manager):
        """Set up mock videos for testing"""

        def get_filename(path):
            if path == "/videos/input/sample_video.mp4":
                return "sample_video.mp4"
            if path == "/videos/input/test_recording.mp4":
                return "test_recording.mp4"
            return ""

        def get_path(filename):
            if filename == "sample_video.mp4":
                return "/videos/input/sample_video.mp4"
            if filename == "test_recording.mp4":
                return "/videos/input/test_recording.mp4"
            return ""

        mock_manager.get_video_filename = get_filename
        mock_manager.get_video_path = get_path

    @patch("graph.videos_manager")
    def test_string_to_config_converts_video_path_to_filename(
        self, mock_videos_manager
    ):
        self._setup_mock_videos(mock_videos_manager)

        pipeline_description = (
            "filesrc location=/videos/input/sample_video.mp4 ! decodebin3 ! fakesink"
        )

        result = Graph.from_pipeline_description(pipeline_description)

        self.assertEqual(len(result.nodes), 3)
        filesrc_node = result.nodes[0]
        self.assertEqual(filesrc_node.type, "filesrc")
        self.assertEqual(filesrc_node.data["location"], "sample_video.mp4")

    @patch("graph.videos_manager")
    def test_config_to_string_converts_video_filename_to_path(
        self, mock_videos_manager
    ):
        self._setup_mock_videos(mock_videos_manager)

        config = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "sample_video.mp4"}),
                Node(id="1", type="decodebin3", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        result = config.to_pipeline_description()

        self.assertIn("location=/videos/input/sample_video.mp4", result)
        self.assertNotIn("location=sample_video.mp4", result)

    @patch("graph.videos_manager")
    def test_multiple_video_properties_conversion(self, mock_videos_manager):
        self._setup_mock_videos(mock_videos_manager)

        pipeline_description = (
            "filesrc location=/videos/input/sample_video.mp4 ! decodebin3 ! "
            "filesink location=/videos/input/test_recording.mp4"
        )

        result = Graph.from_pipeline_description(pipeline_description)

        self.assertEqual(len(result.nodes), 3)
        filesrc_node = result.nodes[0]
        filesink_node = result.nodes[2]

        self.assertEqual(filesrc_node.data["location"], "sample_video.mp4")
        self.assertEqual(filesink_node.data["location"], "test_recording.mp4")

        pipeline_description = result.to_pipeline_description()

        self.assertIn("location=/videos/input/sample_video.mp4", pipeline_description)
        self.assertIn("location=/videos/input/test_recording.mp4", pipeline_description)

    @patch("graph.videos_manager")
    def test_video_path_not_in_recordings_path_unchanged(self, mock_videos_manager):
        mock_videos_manager.get_video_filename.return_value = ""
        mock_videos_manager.get_video_path.return_value = ""

        pipeline_description = (
            "filesrc location=/tmp/external_video.mp4 ! decodebin3 ! fakesink"
        )

        result = Graph.from_pipeline_description(pipeline_description)

        filesrc_node = result.nodes[0]
        self.assertEqual(filesrc_node.data["location"], "/tmp/external_video.mp4")

    @patch("graph.videos_manager")
    @patch("graph.models_manager")
    def test_combined_models_and_videos_conversion(
        self, mock_models_manager, mock_videos_manager
    ):
        # Setup videos
        self._setup_mock_videos(mock_videos_manager)

        # Setup models
        mock_model = MagicMock()
        mock_model.display_name = "Detection Model"
        mock_model.model_path_full = "/models/output/detection.xml"
        mock_model.model_proc_full = ""

        def find_by_path(path):
            if "detection.xml" in path:
                return mock_model
            return None

        def find_by_name(name):
            if name == "Detection Model":
                return mock_model
            return None

        mock_models_manager.find_installed_model_by_model_path_full.side_effect = (
            find_by_path
        )
        mock_models_manager.find_installed_model_by_display_name.side_effect = (
            find_by_name
        )

        pipeline_description = (
            "filesrc location=/videos/input/sample_video.mp4 ! decodebin3 ! "
            "gvadetect model=/models/output/detection.xml ! "
            "filesink location=/videos/input/test_recording.mp4"
        )

        result = Graph.from_pipeline_description(pipeline_description)

        # Check conversions: video paths -> filenames, model path -> display name
        filesrc_node = result.nodes[0]
        gvadetect_node = result.nodes[2]
        filesink_node = result.nodes[3]

        self.assertEqual(filesrc_node.data["location"], "sample_video.mp4")
        self.assertEqual(gvadetect_node.data["model"], "Detection Model")
        self.assertEqual(filesink_node.data["location"], "test_recording.mp4")

        # Round-trip: convert back to string
        pipeline_description = result.to_pipeline_description()

        self.assertIn("location=/videos/input/sample_video.mp4", pipeline_description)
        self.assertIn("model=/models/output/detection.xml", pipeline_description)
        self.assertIn("location=/videos/input/test_recording.mp4", pipeline_description)


class TestNegativeCases(unittest.TestCase):
    def test_circular_graph_returns_empty_string(self):
        """Test that a circular graph is detected and returns empty pipeline description."""
        # Create a circular graph: node 0 -> node 1 -> node 2 -> node 0
        circular_graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(id="2", type="filesink", data={"location": "output.mp4"}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="0"),  # Creates circular reference
            ],
        )

        result = circular_graph.to_pipeline_description()
        self.assertEqual(result, "")

    def test_graph_with_no_start_nodes_returns_empty_string(self):
        """Test that a graph where all nodes are targets returns empty pipeline description."""
        # All nodes are targets (no start nodes)
        no_start_graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(id="1", type="queue", data={}),
            ],
            edges=[
                Edge(id="0", source="2", target="0"),  # References non-existent node
                Edge(id="1", source="2", target="1"),  # References non-existent node
            ],
        )

        result = no_start_graph.to_pipeline_description()
        self.assertEqual(result, "")

    def test_empty_graph_returns_empty_string(self):
        """Test that an empty graph returns empty pipeline description."""
        empty_graph = Graph(nodes=[], edges=[])
        result = empty_graph.to_pipeline_description()
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
