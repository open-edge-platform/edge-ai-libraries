import os
import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch
from graph import Graph, Node, Edge

mock_models_manager = MagicMock()
mock_videos_manager = MagicMock()


def _mock_get_video_filename(path: str) -> str:
    return os.path.basename(path)


def _mock_get_video_path(filename: str) -> str:
    return os.path.join("/tmp", filename)


def _mock_find_model_by_name(name: str):
    mapped_names = [
        "yolov8_license_plate_detector",
        "ch_PP-OCRv4_rec_infer",
        "${MODEL_YOLOv5s_416}+PROC",
        "${MODEL_RESNET}+PROC",
        "${MODEL_YOLOv11n}+PROC",
        "${MODEL_RESNET}+PROC",
        "${MODEL_YOLOv5m}+PROC",
        "${MODEL_RESNET}+PROC",
        "${MODEL_MOBILENET}+PROC",
        "${MODEL_YOLOv11n}+PROC",
        "${MODEL_RESNET}+PROC",
        "${MODEL_MOBILENET}+PROC",
        "${LPR_MODEL}",
        "${OCR_MODEL}",
        "${YOLO11n_POST_MODEL}",
    ]

    if name in mapped_names:
        mock_model = MagicMock()
        mock_model.display_name = name
        return mock_model
    else:
        return None


def _mock_find_model_by_display_name(name: str):
    mock_model = MagicMock()

    if name.startswith("${"):
        mock_model.model_path_full = os.path.join("/models", name)
    else:
        mock_model.model_path_full = os.path.join("/models", f"{name}.xml")

    if name.endswith("+PROC"):
        mock_model.model_proc_full = os.path.join(
            "/models/proc", name.removesuffix("+PROC")
        )
    else:
        mock_model.model_proc_full = ""

    return mock_model


mock_models_manager.find_installed_model_by_name.side_effect = _mock_find_model_by_name
mock_models_manager.find_installed_model_by_display_name.side_effect = (
    _mock_find_model_by_display_name
)
mock_videos_manager.get_video_filename.side_effect = _mock_get_video_filename
mock_videos_manager.get_video_path.side_effect = _mock_get_video_path


@dataclass
class ParseTestCase:
    pipeline_description: str
    pipeline_graph: Graph


parse_test_cases = [
    # old simplevs
    ParseTestCase(
        r"filesrc location=/tmp/license-plate-detection.mp4 ! decodebin3 ! vapostproc ! "
        r"video/x-raw(memory:VAMemory) ! gvafpscounter starting-frame=500 ! "
        r"gvadetect model=/models/yolov8_license_plate_detector.xml model-instance-id=detect0 device=GPU "
        r"pre-process-backend=va-surface-sharing batch-size=0 inference-interval=3 nireq=0 ! queue ! "
        r"gvatrack tracking-type=short-term-imageless ! queue ! "
        r"gvaclassify model=/models/ch_PP-OCRv4_rec_infer.xml "
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
                    data={"location": "license-plate-detection.mp4"},
                ),
                Node(id="1", type="decodebin3", data={}),
                Node(id="2", type="vapostproc", data={}),
                Node(id="3", type="video/x-raw(memory:VAMemory)", data={}),
                Node(id="4", type="gvafpscounter", data={"starting-frame": "500"}),
                Node(
                    id="5",
                    type="gvadetect",
                    data={
                        "model": "yolov8_license_plate_detector",
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
                        "model": "ch_PP-OCRv4_rec_infer",
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
                        "source": "license-plate-detection.mp4",
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
        r"filesrc location=/tmp/song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
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
        r"filesrc location=/tmp/song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! tee name=x ! "
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
        r"filesrc location=/tmp/XXX ! demux ! tee name=t ! queue ! splitmuxsink location=/tmp/output_%02d.mp4 "
        r"t. ! queue ! h264parse ! vah264dec ! "
        r"gvadetect ! queue ! gvatrack ! gvaclassify ! queue ! "
        r"gvawatermark ! gvafpscounter ! gvametaconvert ! gvametapublish ! "
        r"vah264enc ! h264parse ! mp4mux ! filesink location=/tmp/YYY",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "XXX"}),
                Node(id="1", type="demux", data={}),
                Node(id="2", type="tee", data={"name": "t"}),
                Node(id="3", type="queue", data={}),
                Node(
                    id="4",
                    type="splitmuxsink",
                    data={"location": "/tmp/output_%02d.mp4"},
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
                Node(id="20", type="filesink", data={"location": "/tmp/YYY"}),
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
        r"filesrc location=/tmp/${VIDEO} ! qtdemux ! h264parse ! "
        r"tee name=t0 ! queue2 ! splitmuxsink location=/tmp/$(uuid).mp4 "
        r"t0. ! queue2 ! vah264dec ! video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"gvadetect model=/models/${MODEL_YOLOv5s_416}+PROC model-proc=/models/proc/${MODEL_YOLOv5s_416} "
        r"model-instance-id=detect0 pre-process-backend=va-surface-sharing device=GPU "
        r"batch-size=0 inference-interval=3 nireq=0 ! queue2 ! "
        r"gvatrack tracking-type=short-term-imageless ! queue2 ! "
        r"gvaclassify model=/models/${MODEL_RESNET}+PROC model-proc=/models/proc/${MODEL_RESNET} "
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
                        "model": "${MODEL_YOLOv5s_416}+PROC",
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
                        "model": "${MODEL_RESNET}+PROC",
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
                    data={"__node_kind": "caps", "width": "320", "height": "240"},
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
        r"filesrc location=/tmp/${VIDEO} ! qtdemux ! h264parse ! "
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
                    data={"__node_kind": "caps", "width": "320", "height": "240"},
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
        r"filesrc location=/tmp/${VIDEO} ! h265parse ! vah265dec ! "
        r"capsfilter caps=\"video/x-raw(memory:VAMemory)\" ! queue ! "
        r"gvadetect model=/models/${MODEL_YOLOv11n}+PROC model-proc=/models/proc/${MODEL_YOLOv11n} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 threshold=0.5 model-instance-id=yolov11n ! "
        r"queue ! "
        r"gvatrack tracking-type=1 config=tracking_per_class=false ! queue ! "
        r"gvaclassify model=/models/${MODEL_RESNET}+PROC model-proc=/models/proc/${MODEL_RESNET} "
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
                        "model": "${MODEL_YOLOv11n}+PROC",
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
                        "model": "${MODEL_RESNET}+PROC",
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
        r"filesrc location=/tmp/${VIDEO} ! h265parse ! vah265dec ! "
        r"capsfilter caps=\"video/x-raw(memory:VAMemory)\" ! queue ! "
        r"gvadetect model=/models/${MODEL_YOLOv5m}+PROC model-proc=/models/proc/${MODEL_YOLOv5m} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 threshold=0.5 model-instance-id=yolov5m ! "
        r"queue ! "
        r"gvatrack tracking-type=1 config=tracking_per_class=false ! queue ! "
        r"gvaclassify model=/models/${MODEL_RESNET}+PROC model-proc=/models/proc/${MODEL_RESNET} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 inference-region=1 "
        r"model-instance-id=resnet50 ! queue ! "
        r"gvaclassify model=/models/${MODEL_MOBILENET}+PROC model-proc=/models/proc/${MODEL_MOBILENET} "
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
                        "model": "${MODEL_YOLOv5m}+PROC",
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
                        "model": "${MODEL_RESNET}+PROC",
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
                        "model": "${MODEL_MOBILENET}+PROC",
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
        r"filesrc location=/tmp/${VIDEO} ! h265parse ! vah265dec ! "
        r"capsfilter caps=\"video/x-raw(memory:VAMemory)\" ! queue ! "
        r"gvadetect model=/models/${MODEL_YOLOv11n}+PROC model-proc=/models/proc/${MODEL_YOLOv11n} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 threshold=0.5 model-instance-id=yolov11m ! "
        r"queue ! "
        r"gvatrack tracking-type=1 config=tracking_per_class=false ! queue ! "
        r"gvaclassify model=/models/${MODEL_RESNET}+PROC model-proc=/models/proc/${MODEL_RESNET} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"nireq=2 ie-config=NUM_STREAMS=2 batch-size=8 inference-interval=3 inference-region=1 "
        r"model-instance-id=resnet50 ! queue ! "
        r"gvaclassify model=/models/${MODEL_MOBILENET}+PROC model-proc=/models/proc/${MODEL_MOBILENET} "
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
                        "model": "${MODEL_YOLOv11n}+PROC",
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
                        "model": "${MODEL_RESNET}+PROC",
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
                        "model": "${MODEL_MOBILENET}+PROC",
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
        r"filesrc location=/tmp/${VIDEO} ! qtdemux ! h264parse ! vaapidecodebin ! "
        r"vapostproc ! video/x-raw\(memory:VAMemory\) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"gvadetect model=/models/${LPR_MODEL} model-instance-id=detect0 "
        r"pre-process-backend=va-surface-sharing device=GPU batch-size=0 inference-interval=3 nireq=0 ! "
        r"queue2 ! gvatrack tracking-type=short-term-imageless ! queue2 ! "
        r"gvaclassify model=/models/${OCR_MODEL} model-instance-id=classify0 "
        r"pre-process-backend=va-surface-sharing device=GPU batch-size=0 inference-interval=3 nireq=0 "
        r"reclassify-interval=1 ! queue2 ! gvawatermark ! gvametaconvert format=json json-indent=4 ! "
        r"gvametapublish method=file file-path=/dev/null ! "
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
        r"filesrc location=/tmp/${VIDEO} ! qtdemux ! h264parse ! vah264dec ! "
        r"video/x-raw(memory:VAMemory) ! "
        r"gvafpscounter starting-frame=500 ! "
        r"gvadetect model=/models/${YOLO11n_POST_MODEL} "
        r"device=GPU pre-process-backend=va-surface-sharing "
        r"model-instance-id=yolo11-pose ! queue2 ! "
        r"gvatrack tracking-type=short-term-imageless ! "
        r"gvawatermark ! gvametaconvert format=json json-indent=4 ! "
        r"gvametapublish method=file file-path=/dev/null ! "
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
        r"filesrc location=/tmp/${VIDEO} ! qtdemux ! h264parse ! vah264dec ! "
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
        r"filesrc location=/tmp/${VIDEO} ! qtdemux ! h264parse ! vah264dec ! "
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
                    data={"__node_kind": "caps", "width": "320", "height": "240"},
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
    # Caps without parentheses, width/height
    ParseTestCase(
        r"filesrc ! video/x-raw,width=320,height=240 ! fakesink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(
                    id="1",
                    type="video/x-raw",
                    data={"__node_kind": "caps", "width": "320", "height": "240"},
                ),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
    ),
    # Caps with memory feature, simple numeric props
    ParseTestCase(
        r"filesrc ! video/x-raw(memory:NVMM),format=UYVY,width=2592,height=1944,framerate=28/1 ! fakesink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(
                    id="1",
                    type="video/x-raw(memory:NVMM)",
                    data={
                        "__node_kind": "caps",
                        "format": "UYVY",
                        "width": "2592",
                        "height": "1944",
                        "framerate": "28/1",
                    },
                ),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
    ),
    # Caps without memory, with explicit types in values
    ParseTestCase(
        r"filesrc ! video/x-raw,format=(string)UYVY,width=(int)2592,height=(int)1944,framerate=(fraction)28/1 ! fakesink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(
                    id="1",
                    type="video/x-raw",
                    data={
                        "__node_kind": "caps",
                        "format": "(string)UYVY",
                        "width": "(int)2592",
                        "height": "(int)1944",
                        "framerate": "(fraction)28/1",
                    },
                ),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
    ),
    # Caps with memory and explicit types in values
    ParseTestCase(
        r"filesrc ! video/x-raw(memory:NVMM),format=(string)UYVY,width=(int)2592,height=(int)1944,framerate=(fraction)28/1 ! fakesink",
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(
                    id="1",
                    type="video/x-raw(memory:NVMM)",
                    data={
                        "__node_kind": "caps",
                        "format": "(string)UYVY",
                        "width": "(int)2592",
                        "height": "(int)1944",
                        "framerate": "(fraction)28/1",
                    },
                ),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
    ),
]


unsorted_nodes_edges = [
    # gst docs tee example
    ParseTestCase(
        r"filesrc location=/tmp/song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
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
        r"filesrc location=/tmp/song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! audioresample "
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
        r"filesrc location=/tmp/song.ogg ! decodebin ! tee name=t ! queue ! audioconvert ! tee name=x ! "
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


class TestGraphToDescription(unittest.TestCase):
    @patch("graph.models_manager", mock_models_manager)
    @patch("graph.videos_manager", mock_videos_manager)
    def test_graph_to_description(self):
        self.maxDiff = None

        for tc in parse_test_cases + unsorted_nodes_edges:
            actual = tc.pipeline_graph.to_pipeline_description()
            self.assertEqual(actual, tc.pipeline_description)


class TestDescriptionToGraph(unittest.TestCase):
    @patch("graph.models_manager", mock_models_manager)
    @patch("graph.videos_manager", mock_videos_manager)
    def test_description_to_graph(self):
        self.maxDiff = None

        for tc in parse_test_cases:
            actual = Graph.from_pipeline_description(tc.pipeline_description)

            self.assertEqual(len(actual.nodes), len(tc.pipeline_graph.nodes))
            for i in range(len(actual.nodes)):
                actual_node = actual.nodes[i]
                expected_node = tc.pipeline_graph.nodes[i]

                self.assertEqual(actual_node.id, expected_node.id)
                self.assertEqual(actual_node.type, expected_node.type)
                self.assertDictEqual(actual_node.data, expected_node.data)

            self.assertEqual(len(actual.edges), len(tc.pipeline_graph.edges))
            for i in range(len(actual.edges)):
                self.assertEqual(actual.edges[i], tc.pipeline_graph.edges[i])


class TestParseDescription(unittest.TestCase):
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

    def test_edge_ids_unique_for_consecutive_caps_nodes(self):
        """
        When multiple caps segments appear in sequence, edge IDs must remain
        unique across all edges in the graph.

        Example:
            filesrc ! video/x-raw,width=320,height=240 ! video/x-raw,format=NV12 ! fakesink
        """
        pipeline = (
            "filesrc ! "
            "video/x-raw,width=320,height=240 ! "
            "video/x-raw,format=NV12 ! "
            "fakesink"
        )
        result = Graph.from_pipeline_description(pipeline)

        # We expect 4 nodes: filesrc, caps1, caps2, fakesink
        self.assertEqual(len(result.nodes), 4)
        # And 3 edges: 0->1, 1->2, 2->3
        self.assertEqual(len(result.edges), 3)

        # Edge IDs must be unique strings
        edge_ids = [e.id for e in result.edges]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))

        # Sanity-check the connectivity: ids should form a simple chain.
        sources_targets = [(e.source, e.target) for e in result.edges]
        self.assertIn(("0", "1"), sources_targets)
        self.assertIn(("1", "2"), sources_targets)
        self.assertIn(("2", "3"), sources_targets)

    def test_edge_ids_unique_with_single_caps_segment(self):
        """
        Basic sanity check that even with a single caps segment the edge IDs
        remain unique and correctly represent the chain.
        """
        pipeline = "filesrc ! video/x-raw,width=320,height=240 ! fakesink"
        result = Graph.from_pipeline_description(pipeline)

        # filesrc, caps, fakesink
        self.assertEqual(len(result.nodes), 3)
        self.assertEqual(len(result.edges), 2)

        edge_ids = [e.id for e in result.edges]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))

        sources_targets = [(e.source, e.target) for e in result.edges]
        self.assertIn(("0", "1"), sources_targets)
        self.assertIn(("1", "2"), sources_targets)

    def test_tee_end_without_tee_element_raises_error_for_regular_node(self):
        """
        Using a tee endpoint (e.g. 't.') without a corresponding tee element
        should raise a clear ValueError instead of an IndexError.

        This test covers the case where TEE_END is followed by a regular
        element segment.
        """
        # There is no 'tee name=t0' element, but 't0.' is used.
        pipeline = "filesrc ! t0. ! queue ! fakesink"

        with self.assertRaises(ValueError) as cm:
            Graph.from_pipeline_description(pipeline)

        self.assertIn("TEE_END without corresponding tee element", str(cm.exception))

    def test_tee_end_without_tee_element_raises_error_for_caps_node(self):
        """
        Using a tee endpoint (e.g. 't.') without a corresponding tee element
        should also raise a clear ValueError when the next segment is a caps
        node.
        """
        pipeline = "filesrc ! t0. ! video/x-raw,width=320,height=240 ! fakesink"

        with self.assertRaises(ValueError) as cm:
            Graph.from_pipeline_description(pipeline)

        self.assertIn("TEE_END without corresponding tee element", str(cm.exception))


class TestNegativeCases(unittest.TestCase):
    @patch("graph.videos_manager", mock_videos_manager)
    def test_circular_graph_raises_error(self):
        """Test that a circular graph is detected and raises an error."""
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

        with self.assertRaises(ValueError) as cm:
            circular_graph.to_pipeline_description()
        self.assertIn("circular graph", str(cm.exception))

    def test_graph_with_no_start_nodes_raises_error(self):
        """Test that a graph where all nodes are targets raises an error."""
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

        with self.assertRaises(ValueError) as cm:
            no_start_graph.to_pipeline_description()
        self.assertIn("no start nodes", str(cm.exception))

    def test_empty_graph_raises_error(self):
        """Test that an empty graph raises an error."""
        empty_graph = Graph(nodes=[], edges=[])
        with self.assertRaises(ValueError) as cm:
            empty_graph.to_pipeline_description()
        self.assertIn("Empty graph", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
