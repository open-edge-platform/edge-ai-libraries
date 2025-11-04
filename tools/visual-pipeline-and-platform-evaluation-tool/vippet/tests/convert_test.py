import re
import unittest
from dataclasses import dataclass

from convert import Config, Node, Edge, config_to_string, string_to_config, _tokenize


@dataclass
class ParseTestCase:
    launch_string: str
    launch_dict: Config


parse_test_cases = [
    ParseTestCase(
        # old simplevs
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
        Config(
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
    ParseTestCase(
        # gst docs tee example
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
        r"! autoaudiosink t. ! queue ! audioconvert ! goom ! videoconvert ! autovideosink",
        Config(
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
    ParseTestCase(
        # 2 nested tees
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! tee name=x ! "
        r"queue ! audiorate ! autoaudiosink x. ! queue ! audioresample ! autoaudiosink t. ! queue "
        r"! audioconvert ! goom ! videoconvert ! autovideosink",
        Config(
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
    ParseTestCase(
        # template
        r"filesrc location=XXX ! demux ! tee name=t ! queue ! splitmuxsink location=output_%02d.mp4 "
        r"t. ! queue ! h264parse ! vah264dec ! "
        r"gvadetect ! queue ! gvatrack ! gvaclassify ! queue ! "
        r"gvawatermark ! gvafpscounter ! gvametaconvert ! gvametapublish ! "
        r"vah264enc ! h264parse ! mp4mux ! filesink location=YYY",
        Config(
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
    ParseTestCase(
        # SmartNVR Analytics Branch
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
        Config(
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
    ParseTestCase(
        # SmartNVR Media-only Branch
        r"filesrc location=${VIDEO} ! qtdemux ! h264parse ! "
        r"tee name=t0 ! queue2 ! splitmuxsink location=/tmp/$(uuid).mp4 "
        r"t0. ! queue2 ! vah264dec ! video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"vapostproc ! video/x-raw\(memory:VAMemory\),width=320,height=240 ! fakesink",
        Config(
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
        Config(
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
    ParseTestCase(
        # Magic 9 Medium
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
        Config(
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
    ParseTestCase(
        # Magic 9 Heavy
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
        Config(
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
    ParseTestCase(
        # Simple Video Structuration
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
        Config(
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
        Config(
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
    ParseTestCase(
        # Video Decode Pipeline
        r"filesrc location=${VIDEO} ! qtdemux ! h264parse ! vah264dec ! "
        r"video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"fakesink",
        Config(
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
    ParseTestCase(
        # Video Decode Scale Pipeline
        r"filesrc location=${VIDEO} ! qtdemux ! h264parse ! vah264dec ! "
        r"video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"vapostproc ! video/x-raw\(memory:VAMemory\),width=320,height=240 ! fakesink",
        Config(
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
    ParseTestCase(
        # gst docs tee example
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
        r"! autoaudiosink t. ! queue ! audioconvert ! goom ! videoconvert ! autovideosink",
        Config(
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
    ParseTestCase(
        # gst docs tee example, ids start from 1
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
        r"! autoaudiosink t. ! queue ! audioconvert ! goom ! videoconvert ! autovideosink",
        Config(
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
    ParseTestCase(
        # 2 nested tees
        r"filesrc location=song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! tee name=x ! "
        r"queue ! audiorate ! autoaudiosink x. ! queue ! audioresample ! autoaudiosink t. ! queue "
        r"! audioconvert ! goom ! videoconvert ! autovideosink",
        Config(
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
    s = re.sub(r",", " ", s)
    s = re.sub(r" {2,}", " ", s)
    s = re.sub(r"(?<!\s)!", " !", s)
    s = re.sub(r"!(?!\s)", "! ", s)
    return s


class TestDictToString(unittest.TestCase):
    def test_dict_to_string(self):
        self.maxDiff = None

        for tc in parse_test_cases:
            actual = config_to_string(tc.launch_dict)
            self.assertEqual(actual, normalize(tc.launch_string))

        for tc in unsorted_nodes_edges:
            actual = config_to_string(tc.launch_dict)
            self.assertEqual(actual, normalize(tc.launch_string))


class TestParseLaunchString(unittest.TestCase):
    def test_parsing(self):
        self.maxDiff = None

        for tc in parse_test_cases:
            actual = string_to_config(tc.launch_string)
            self.assertEqual(actual, tc.launch_dict)

    def test_empty_pipeline(self):
        pipeline = ""
        result = string_to_config(pipeline)

        self.assertEqual(len(result.nodes), 0)
        self.assertEqual(len(result.edges), 0)

    def test_single_element(self):
        pipeline = "filesrc"
        result = string_to_config(pipeline)

        self.assertEqual(len(result.nodes), 1)
        self.assertEqual(result.nodes[0].type, "filesrc")
        self.assertEqual(len(result.edges), 0)

    def test_caps_filter(self):
        # Caps filters like "video/x-raw(memory:VAMemory)" should be parsed
        pipeline = "filesrc ! video/x-raw(memory:VAMemory) ! filesink"
        result = string_to_config(pipeline)

        self.assertEqual(len(result.nodes), 3)
        self.assertTrue(
            any(n.type == "video/x-raw(memory:VAMemory)" for n in result.nodes)
        )

    def test_node_ids_are_sequential(self):
        pipeline = "filesrc ! queue ! filesink"
        result = string_to_config(pipeline)

        self.assertEqual(result.nodes[0].id, "0")
        self.assertEqual(result.nodes[1].id, "1")
        self.assertEqual(result.nodes[2].id, "2")

    def test_edge_ids_are_sequential(self):
        pipeline = "filesrc ! queue ! filesink"
        result = string_to_config(pipeline)

        self.assertEqual(result.edges[0].id, "0")
        self.assertEqual(result.edges[1].id, "1")


class TestTokenize(unittest.TestCase):
    def test_simple_element_type(self):
        tokens = list(_tokenize("filesrc"))
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].kind, "TYPE")
        self.assertEqual(tokens[0].value, "filesrc")

    def test_property(self):
        tokens = list(_tokenize("location=/tmp/file.mp4"))
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].kind, "PROPERTY")
        self.assertEqual(tokens[0].value, "location=/tmp/file.mp4")

    def test_property_with_spaces(self):
        tokens = list(_tokenize("dummy   = value"))
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].kind, "PROPERTY")
        self.assertEqual(tokens[0].value, "dummy   = value")

    def test_tee_end(self):
        tokens = list(_tokenize("t."))
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].kind, "TEE_END")
        self.assertEqual(tokens[0].value, "t.")

    def test_element_with_property(self):
        tokens = list(_tokenize("filesrc location=/tmp/file.mp4"))
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].kind, "TYPE")
        self.assertEqual(tokens[0].value, "filesrc")
        self.assertEqual(tokens[1].kind, "PROPERTY")
        self.assertEqual(tokens[1].value, "location=/tmp/file.mp4")

    def test_element_with_multiple_properties(self):
        tokens = list(_tokenize("vah264enc bitrate=5000 quality=4"))
        self.assertEqual(len(tokens), 3)
        self.assertEqual(tokens[0].kind, "TYPE")
        self.assertEqual(tokens[0].value, "vah264enc")
        self.assertEqual(tokens[1].kind, "PROPERTY")
        self.assertEqual(tokens[1].value, "bitrate=5000")
        self.assertEqual(tokens[2].kind, "PROPERTY")
        self.assertEqual(tokens[2].value, "quality=4")

    def test_tee_name(self):
        tokens = list(_tokenize("tee name=t"))
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].kind, "TYPE")
        self.assertEqual(tokens[0].value, "tee")
        self.assertEqual(tokens[1].kind, "PROPERTY")
        self.assertEqual(tokens[1].value, "name=t")


if __name__ == "__main__":
    unittest.main()
