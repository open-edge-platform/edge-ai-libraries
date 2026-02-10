import re
import os
import unittest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock, patch

from graph import Edge, Graph, Node
from video_encoder import ENCODER_DEVICE_CPU, ENCODER_DEVICE_GPU

# Create mock instances for SupportedModelsManager and VideosManager
mock_models_manager_instance = MagicMock()
mock_videos_manager_instance = MagicMock()


def _mock_get_video_filename(path: str) -> str:
    return os.path.basename(path)


def _mock_get_video_path(filename: str) -> str:
    return os.path.join("/tmp", filename)


def _mock_find_installed_model_by_model_and_proc_path(
    model_path: str, model_proc_path: Optional[str] = None
):
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

    base_name = os.path.splitext(os.path.basename(model_path))[0]

    if base_name in mapped_names:
        mock_model = MagicMock()
        mock_model.display_name = base_name
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


mock_models_manager_instance.find_installed_model_by_model_and_proc_path.side_effect = (
    _mock_find_installed_model_by_model_and_proc_path
)
mock_models_manager_instance.find_installed_model_by_display_name.side_effect = (
    _mock_find_model_by_display_name
)
mock_videos_manager_instance.get_video_filename.side_effect = _mock_get_video_filename
mock_videos_manager_instance.get_video_path.side_effect = _mock_get_video_path


@dataclass
class ParseTestCase:
    pipeline_description: str
    pipeline_graph: Graph
    pipeline_graph_simple: Graph


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
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "license-plate-detection.mp4"},
                ),
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
                Node(
                    id="7",
                    type="gvatrack",
                    data={"tracking-type": "short-term-imageless"},
                ),
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
                Node(
                    id="17",
                    type="filesink",
                    data={"location": "/tmp/license-plate-detection-output.mp4"},
                ),
            ],
            edges=[
                Edge(id="0", source="0", target="4"),
                Edge(id="1", source="4", target="5"),
                Edge(id="2", source="5", target="7"),
                Edge(id="3", source="7", target="9"),
                Edge(id="4", source="9", target="11"),
                Edge(id="5", source="11", target="12"),
                Edge(id="6", source="12", target="13"),
                Edge(id="7", source="13", target="17"),
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
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "song.ogg"},
                ),
                Node(id="6", type="autoaudiosink", data={}),
                Node(id="11", type="autovideosink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="6"),
                Edge(id="1", source="0", target="11"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "song.ogg"}),
                Node(id="8", type="autoaudiosink", data={}),
                Node(id="11", type="autoaudiosink", data={}),
                Node(id="16", type="autovideosink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="8"),
                Edge(id="1", source="0", target="11"),
                Edge(id="2", source="0", target="16"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "XXX"}),
                Node(
                    id="4",
                    type="splitmuxsink",
                    data={"location": "/tmp/output_%02d.mp4"},
                ),
                Node(id="8", type="gvadetect", data={}),
                Node(id="10", type="gvatrack", data={}),
                Node(id="11", type="gvaclassify", data={}),
                Node(id="13", type="gvawatermark", data={}),
                Node(id="14", type="gvafpscounter", data={}),
                Node(id="15", type="gvametaconvert", data={}),
                Node(id="16", type="gvametapublish", data={}),
                Node(id="20", type="filesink", data={"location": "/tmp/YYY"}),
            ],
            edges=[
                Edge(id="0", source="0", target="4"),
                Edge(id="1", source="0", target="8"),
                Edge(id="2", source="8", target="10"),
                Edge(id="3", source="10", target="11"),
                Edge(id="4", source="11", target="13"),
                Edge(id="5", source="13", target="14"),
                Edge(id="6", source="14", target="15"),
                Edge(id="7", source="15", target="16"),
                Edge(id="8", source="16", target="20"),
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
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
                Node(
                    id="5",
                    type="splitmuxsink",
                    data={"location": "/tmp/$(uuid).mp4"},
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
                Node(
                    id="12",
                    type="gvatrack",
                    data={"tracking-type": "short-term-imageless"},
                ),
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
                Node(id="21", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="5"),
                Edge(id="1", source="0", target="9"),
                Edge(id="2", source="9", target="10"),
                Edge(id="3", source="10", target="12"),
                Edge(id="4", source="12", target="14"),
                Edge(id="5", source="14", target="16"),
                Edge(id="6", source="16", target="17"),
                Edge(id="7", source="17", target="18"),
                Edge(id="8", source="18", target="21"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
                Node(
                    id="5",
                    type="splitmuxsink",
                    data={"location": "/tmp/$(uuid).mp4"},
                ),
                Node(id="9", type="gvafpscounter", data={"starting-frame": "500"}),
                Node(id="12", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="5"),
                Edge(id="1", source="0", target="9"),
                Edge(id="2", source="9", target="12"),
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
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
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
                Node(
                    id="7",
                    type="gvatrack",
                    data={
                        "tracking-type": "1",
                        "config": "tracking_per_class=false",
                    },
                ),
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
                Edge(id="0", source="0", target="5"),
                Edge(id="1", source="5", target="7"),
                Edge(id="2", source="7", target="9"),
                Edge(id="3", source="9", target="11"),
                Edge(id="4", source="11", target="12"),
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
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
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
                Node(
                    id="7",
                    type="gvatrack",
                    data={
                        "tracking-type": "1",
                        "config": "tracking_per_class=false",
                    },
                ),
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
                Edge(id="0", source="0", target="5"),
                Edge(id="1", source="5", target="7"),
                Edge(id="2", source="7", target="9"),
                Edge(id="3", source="9", target="11"),
                Edge(id="4", source="11", target="13"),
                Edge(id="5", source="13", target="14"),
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
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
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
                Node(
                    id="7",
                    type="gvatrack",
                    data={
                        "tracking-type": "1",
                        "config": "tracking_per_class=false",
                    },
                ),
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
                Edge(id="0", source="0", target="5"),
                Edge(id="1", source="5", target="7"),
                Edge(id="2", source="7", target="9"),
                Edge(id="3", source="9", target="11"),
                Edge(id="4", source="11", target="13"),
                Edge(id="5", source="13", target="14"),
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
        Graph(
            nodes=[
                Node(
                    id="0",
                    type="filesrc",
                    data={"location": "${VIDEO}"},
                ),
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
                Node(
                    id="9",
                    type="gvatrack",
                    data={"tracking-type": "short-term-imageless"},
                ),
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
                Edge(id="0", source="0", target="6"),
                Edge(id="1", source="6", target="7"),
                Edge(id="2", source="7", target="9"),
                Edge(id="3", source="9", target="11"),
                Edge(id="4", source="11", target="13"),
                Edge(id="5", source="13", target="14"),
                Edge(id="6", source="14", target="15"),
                Edge(id="7", source="15", target="16"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
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
                Edge(id="0", source="0", target="5"),
                Edge(id="1", source="5", target="6"),
                Edge(id="2", source="6", target="8"),
                Edge(id="3", source="8", target="9"),
                Edge(id="4", source="9", target="10"),
                Edge(id="5", source="10", target="11"),
                Edge(id="6", source="11", target="12"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
                Node(
                    id="5",
                    type="gvafpscounter",
                    data={"starting-frame": "500"},
                ),
                Node(id="6", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="5"),
                Edge(id="1", source="5", target="6"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "${VIDEO}"}),
                Node(id="5", type="gvafpscounter", data={"starting-frame": "500"}),
                Node(id="8", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="5"),
                Edge(id="1", source="5", target="8"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "song.ogg"}),
                Node(id="6", type="autoaudiosink", data={}),
                Node(id="11", type="autovideosink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="6"),
                Edge(id="1", source="0", target="11"),
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
        Graph(
            nodes=[
                Node(id="1", type="filesrc", data={"location": "song.ogg"}),
                Node(id="7", type="autoaudiosink", data={}),
                Node(id="12", type="autovideosink", data={}),
            ],
            edges=[
                Edge(id="0", source="1", target="7"),
                Edge(id="1", source="1", target="12"),
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
        Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "song.ogg"}),
                Node(id="8", type="autoaudiosink", data={}),
                Node(id="11", type="autoaudiosink", data={}),
                Node(id="16", type="autovideosink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="8"),
                Edge(id="1", source="0", target="11"),
                Edge(id="2", source="0", target="16"),
            ],
        ),
    ),
]


@dataclass
class GraphTestCase:
    pipeline_description: str
    original_pipeline_graph: Graph
    original_pipeline_graph_simple: Graph
    modified_pipeline_graph_simple: Graph
    modified_pipeline_graph: Graph


# Positive test cases for apply_simple_view_changes
# These test cases verify that property modifications are correctly applied
apply_simple_view_changes_positive_test_cases = [
    # Test case: Modify single node property
    GraphTestCase(
        pipeline_description="test_modify_single_property",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(id="2", type="gvadetect", data={"model": "yolo", "device": "GPU"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="2", type="gvadetect", data={"model": "yolo", "device": "GPU"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
                Edge(id="1", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="2", type="gvadetect", data={"model": "yolo", "device": "CPU"}
                ),  # Changed GPU -> CPU
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
                Edge(id="1", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(
                    id="2", type="gvadetect", data={"model": "yolo", "device": "CPU"}
                ),  # Changed GPU -> CPU
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
    ),
    # Test case: Modify multiple node properties
    GraphTestCase(
        pipeline_description="test_modify_multiple_properties",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "input.mp4"}),
                Node(
                    id="1",
                    type="gvadetect",
                    data={"model": "yolo", "device": "GPU", "threshold": "0.5"},
                ),
                Node(
                    id="2",
                    type="gvaclassify",
                    data={"model": "resnet", "device": "GPU"},
                ),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "input.mp4"}),
                Node(
                    id="1",
                    type="gvadetect",
                    data={"model": "yolo", "device": "GPU", "threshold": "0.5"},
                ),
                Node(
                    id="2",
                    type="gvaclassify",
                    data={"model": "resnet", "device": "GPU"},
                ),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "input.mp4"}),
                Node(
                    id="1",
                    type="gvadetect",
                    data={"model": "yolo", "device": "CPU", "threshold": "0.7"},
                ),  # Changed device and threshold
                Node(
                    id="2",
                    type="gvaclassify",
                    data={"model": "mobilenet", "device": "CPU"},
                ),  # Changed model and device
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "input.mp4"}),
                Node(
                    id="1",
                    type="gvadetect",
                    data={"model": "yolo", "device": "CPU", "threshold": "0.7"},
                ),
                Node(
                    id="2",
                    type="gvaclassify",
                    data={"model": "mobilenet", "device": "CPU"},
                ),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
    ),
    # Test case: No changes (identity test)
    GraphTestCase(
        pipeline_description="test_no_changes",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        modified_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
    ),
    # Test case: Add new property to existing node
    GraphTestCase(
        pipeline_description="test_add_property",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(id="2", type="gvadetect", data={"model": "yolo"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="2", type="gvadetect", data={"model": "yolo"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
                Edge(id="1", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="2", type="gvadetect", data={"model": "yolo", "device": "GPU"}
                ),  # Added device property
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
                Edge(id="1", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(
                    id="2", type="gvadetect", data={"model": "yolo", "device": "GPU"}
                ),  # Added device property
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
    ),
    # Test case: Remove property from existing node
    GraphTestCase(
        pipeline_description="test_remove_property",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="1",
                    type="gvadetect",
                    data={"model": "yolo", "device": "GPU", "threshold": "0.5"},
                ),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="1",
                    type="gvadetect",
                    data={"model": "yolo", "device": "GPU", "threshold": "0.5"},
                ),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="1", type="gvadetect", data={"model": "yolo", "device": "GPU"}
                ),  # Removed threshold property
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        modified_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="1", type="gvadetect", data={"model": "yolo", "device": "GPU"}
                ),  # Removed threshold property
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
    ),
]


# Negative test cases for apply_simple_view_changes
# These test cases verify that unsupported operations raise appropriate errors
@dataclass
class NegativeGraphTestCase:
    test_name: str
    original_pipeline_graph: Graph
    original_pipeline_graph_simple: Graph
    modified_pipeline_graph_simple: Graph
    expected_error_message: str


apply_simple_view_changes_negative_test_cases = [
    # Test case: Add new edge
    NegativeGraphTestCase(
        test_name="test_add_edge",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(id="2", type="gvadetect", data={"model": "yolo"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="2", type="gvadetect", data={"model": "yolo"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
                Edge(id="1", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="2", type="gvadetect", data={"model": "yolo"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
                Edge(id="1", source="2", target="3"),
                Edge(id="2", source="0", target="3"),  # New edge added
            ],
        ),
        expected_error_message="Edge additions are not supported in simple view",
    ),
    # Test case: Remove edge
    NegativeGraphTestCase(
        test_name="test_remove_edge",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                # Edge from 1 to 2 removed
            ],
        ),
        expected_error_message="Edge removals are not supported in simple view",
    ),
    # Test case: Modify edge source
    NegativeGraphTestCase(
        test_name="test_modify_edge_source",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvaclassify", data={"model": "resnet"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvaclassify", data={"model": "resnet"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvaclassify", data={"model": "resnet"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="0", target="2"),  # Changed source from 1 to 0
                Edge(id="2", source="2", target="3"),
            ],
        ),
        expected_error_message="Edge modifications are not supported in simple view",
    ),
    # Test case: Modify edge target
    NegativeGraphTestCase(
        test_name="test_modify_edge_target",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvaclassify", data={"model": "resnet"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvaclassify", data={"model": "resnet"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvaclassify", data={"model": "resnet"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="3"),  # Changed target from 2 to 3
                Edge(id="2", source="2", target="3"),
            ],
        ),
        expected_error_message="Edge modifications are not supported in simple view",
    ),
    # Test case: Add new node
    NegativeGraphTestCase(
        test_name="test_add_node",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
                Node(id="3", type="gvatrack", data={}),  # New node added
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        expected_error_message="Node additions are not supported in simple view",
    ),
    # Test case: Remove node
    NegativeGraphTestCase(
        test_name="test_remove_node",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvatrack", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvatrack", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                # Node id="2" removed
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="3"),
            ],
        ),
        expected_error_message="Node removals are not supported in simple view",
    ),
    # Test case: Change node type
    NegativeGraphTestCase(
        test_name="test_change_node_type",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="1", type="gvaclassify", data={"model": "yolo"}
                ),  # Changed type from gvadetect to gvaclassify
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        ),
        expected_error_message="Node type changes are not supported in simple view",
    ),
    # Test case: Multiple edges added
    NegativeGraphTestCase(
        test_name="test_multiple_edges_added",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvatrack", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvatrack", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvatrack", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="0", target="2"),  # Added edge
                Edge(id="4", source="1", target="3"),  # Added edge
            ],
        ),
        expected_error_message="Edge additions are not supported in simple view",
    ),
    # Test case: Multiple nodes removed
    NegativeGraphTestCase(
        test_name="test_multiple_nodes_removed",
        original_pipeline_graph=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvatrack", data={}),
                Node(id="3", type="gvaclassify", data={"model": "resnet"}),
                Node(id="4", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
            ],
        ),
        original_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvatrack", data={}),
                Node(id="3", type="gvaclassify", data={"model": "resnet"}),
                Node(id="4", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
            ],
        ),
        modified_pipeline_graph_simple=Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                # Nodes 2, 3 removed
                Node(id="4", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="4"),
            ],
        ),
        expected_error_message="Node removals are not supported in simple view",
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
    @patch("graph.SupportedModelsManager")
    @patch("graph.VideosManager")
    def test_graph_to_description(self, mock_videos_cls, mock_models_cls):
        mock_videos_cls.return_value = mock_videos_manager_instance
        mock_models_cls.return_value = mock_models_manager_instance

        self.maxDiff = None

        for tc in parse_test_cases + unsorted_nodes_edges:
            actual = tc.pipeline_graph.to_pipeline_description()
            self.assertEqual(actual, tc.pipeline_description)


class TestDescriptionToGraph(unittest.TestCase):
    @patch("graph.SupportedModelsManager")
    @patch("graph.VideosManager")
    def test_description_to_graph(self, mock_videos_cls, mock_models_cls):
        mock_videos_cls.return_value = mock_videos_manager_instance
        mock_models_cls.return_value = mock_models_manager_instance

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
    @patch("graph.VideosManager")
    def test_circular_graph_raises_error(self, mock_videos_cls):
        """Test that a circular graph is detected and raises an error."""
        mock_videos_cls.return_value = mock_videos_manager_instance

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


class TestGetRecommendedEncoderDevice(unittest.TestCase):
    """Test cases for Graph.get_recommended_encoder_device method."""

    def test_gpu_encoder_for_va_memory_caps(self):
        """Test that GPU encoder is recommended when video/x-raw(memory:VAMemory) is found."""
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="decodebin3", data={}),
                Node(
                    id="2",
                    type="video/x-raw(memory:VAMemory)",
                    data={"__node_kind": "caps"},
                ),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )

        self.assertEqual(graph.get_recommended_encoder_device(), ENCODER_DEVICE_GPU)

    def test_cpu_encoder_for_standard_video_raw(self):
        """Test that CPU encoder is recommended for standard video/x-raw caps."""
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="decodebin3", data={}),
                Node(
                    id="2",
                    type="video/x-raw",
                    data={"__node_kind": "caps", "width": "640", "height": "480"},
                ),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )

        self.assertEqual(graph.get_recommended_encoder_device(), ENCODER_DEVICE_CPU)

    def test_cpu_encoder_when_no_video_raw_caps(self):
        """Test that CPU encoder is recommended when no video/x-raw caps exist."""
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="decodebin3", data={}),
                Node(id="2", type="queue", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )

        self.assertEqual(graph.get_recommended_encoder_device(), ENCODER_DEVICE_CPU)

    def test_uses_last_video_raw_caps_when_multiple_exist(self):
        """Test that the method uses the last video/x-raw caps in the pipeline."""
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="1",
                    type="video/x-raw",
                    data={"__node_kind": "caps", "width": "640"},
                ),
                Node(id="2", type="queue", data={}),
                Node(
                    id="3",
                    type="video/x-raw(memory:VAMemory)",
                    data={"__node_kind": "caps"},
                ),
                Node(id="4", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
            ],
        )

        # Should return GPU because the last video/x-raw has VAMemory
        self.assertEqual(graph.get_recommended_encoder_device(), ENCODER_DEVICE_GPU)

    def test_iterates_backwards_through_nodes(self):
        """Test that the method iterates backwards (uses last occurrence, not first)."""
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="1",
                    type="video/x-raw(memory:VAMemory)",
                    data={"__node_kind": "caps"},
                ),
                Node(id="2", type="queue", data={}),
                Node(
                    id="3", type="video/x-raw", data={"__node_kind": "caps"}
                ),  # Last one, no VAMemory
                Node(id="4", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
            ],
        )

        # Should return CPU because iterating backwards finds node 3 first (no VAMemory)
        self.assertEqual(graph.get_recommended_encoder_device(), ENCODER_DEVICE_CPU)

    def test_empty_graph(self):
        """Test that CPU encoder is recommended for an empty graph."""
        graph = Graph(nodes=[], edges=[])

        self.assertEqual(graph.get_recommended_encoder_device(), ENCODER_DEVICE_CPU)


class TestToSimpleView(unittest.TestCase):
    """
    Test the to_simple_view method which generates simplified graphs
    by filtering out technical elements and reconnecting visible nodes.
    """

    @patch("graph.SIMPLE_VIEW_INVISIBLE_ELEMENTS", "")
    @patch("graph._COMPILED_INVISIBLE_PATTERNS", [])
    def test_simple_view_generation(self):
        """
        Test that to_simple_view() generates the expected simplified graphs.

        This test verifies that:
        - Only elements matching the visible patterns (*src, urisourcebin, gva*, *sink) are kept
        - Hidden technical elements (queue, tee, capsfilter, etc.) are removed
        - Caps nodes are always hidden regardless of type
        - Edges are properly reconnected through hidden nodes
        - Node IDs of visible elements are preserved
        - Edge IDs are regenerated sequentially
        """
        self.maxDiff = None

        for tc in parse_test_cases + unsorted_nodes_edges:
            with self.subTest(pipeline=tc.pipeline_description[:200] + "..."):
                actual_simple = tc.pipeline_graph.to_simple_view()

                # Check that the number of nodes matches expected
                self.assertEqual(
                    len(actual_simple.nodes),
                    len(tc.pipeline_graph_simple.nodes),
                    f"Number of nodes mismatch for: {tc.pipeline_description[:200]}...",
                )

                # Check each node matches expected (preserving order)
                for i, (actual_node, expected_node) in enumerate(
                    zip(actual_simple.nodes, tc.pipeline_graph_simple.nodes)
                ):
                    self.assertEqual(
                        actual_node.id,
                        expected_node.id,
                        f"Node {i} ID mismatch: expected {expected_node.id}, got {actual_node.id}",
                    )
                    self.assertEqual(
                        actual_node.type,
                        expected_node.type,
                        f"Node {i} type mismatch: expected {expected_node.type}, got {actual_node.type}",
                    )
                    self.assertDictEqual(
                        actual_node.data, expected_node.data, f"Node {i} data mismatch"
                    )

                # Check that the number of edges matches expected
                self.assertEqual(
                    len(actual_simple.edges),
                    len(tc.pipeline_graph_simple.edges),
                    f"Number of edges mismatch for: {tc.pipeline_description[:200]}...",
                )

                # Check each edge matches expected (preserving connectivity)
                for i, (actual_edge, expected_edge) in enumerate(
                    zip(actual_simple.edges, tc.pipeline_graph_simple.edges)
                ):
                    self.assertEqual(
                        actual_edge.source,
                        expected_edge.source,
                        f"Edge {i} source mismatch: expected {expected_edge.source}, got {actual_edge.source}",
                    )
                    self.assertEqual(
                        actual_edge.target,
                        expected_edge.target,
                        f"Edge {i} target mismatch: expected {expected_edge.target}, got {actual_edge.target}",
                    )
                    # Edge IDs should be regenerated sequentially
                    self.assertEqual(
                        actual_edge.id,
                        str(i),
                        f"Edge {i} ID should be sequential: expected {str(i)}, got {actual_edge.id}",
                    )

    @patch("graph.SIMPLE_VIEW_INVISIBLE_ELEMENTS", "gvafpscounter,gvametapublish")
    def test_simple_view_with_invisible_elements(self):
        """
        Test that SIMPLE_VIEW_INVISIBLE_ELEMENTS excludes specified elements.

        This test verifies that:
        - Elements matching invisible patterns are excluded even if they match visible patterns
        - Other visible elements (like gvametaconvert, gvadetect) remain visible
        - Edges are properly reconnected through the newly hidden nodes
        """
        # Compile the test-specific invisible patterns
        test_invisible_patterns = [
            re.compile("^gvafpscounter$"),
            re.compile("^gvametapublish$"),
        ]

        # Create a graph with gvafpscounter and gvametapublish that should be hidden
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(id="2", type="gvadetect", data={"model": "yolo"}),
                Node(id="3", type="gvafpscounter", data={"starting-frame": "500"}),
                Node(id="4", type="gvametaconvert", data={"format": "json"}),
                Node(id="5", type="gvametapublish", data={"method": "file"}),
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
        )

        with patch("graph._COMPILED_INVISIBLE_PATTERNS", test_invisible_patterns):
            simple_view = graph.to_simple_view()

            # Expected: filesrc, gvadetect, gvametaconvert, fakesink
            # gvafpscounter and gvametapublish should be excluded
            expected_node_types = ["filesrc", "gvadetect", "gvametaconvert", "fakesink"]
            actual_node_types = [node.type for node in simple_view.nodes]

            self.assertEqual(actual_node_types, expected_node_types)

            # Check edges are properly reconnected
            self.assertEqual(len(simple_view.edges), 3)
            # filesrc -> gvadetect
            self.assertEqual(simple_view.edges[0].source, "0")
            self.assertEqual(simple_view.edges[0].target, "2")
            # gvadetect -> gvametaconvert
            self.assertEqual(simple_view.edges[1].source, "2")
            self.assertEqual(simple_view.edges[1].target, "4")
            # gvametaconvert -> fakesink
            self.assertEqual(simple_view.edges[2].source, "4")
            self.assertEqual(simple_view.edges[2].target, "6")

    def test_simple_view_invisible_wildcard_pattern(self):
        """
        Test that wildcard patterns work in SIMPLE_VIEW_INVISIBLE_ELEMENTS.

        This test verifies that a wildcard pattern like 'gva*' excludes all gva elements.
        """
        # Compile wildcard pattern: gva*
        test_invisible_patterns = [re.compile("^gva.*$")]

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvadetect", data={"model": "yolo"}),
                Node(id="2", type="gvametaconvert", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )

        with patch("graph._COMPILED_INVISIBLE_PATTERNS", test_invisible_patterns):
            simple_view = graph.to_simple_view()

            # All gva* elements should be hidden
            expected_node_types = ["filesrc", "fakesink"]
            actual_node_types = [node.type for node in simple_view.nodes]

            self.assertEqual(actual_node_types, expected_node_types)

            # Direct edge from filesrc to fakesink
            self.assertEqual(len(simple_view.edges), 1)
            self.assertEqual(simple_view.edges[0].source, "0")
            self.assertEqual(simple_view.edges[0].target, "3")

    @patch("graph._COMPILED_INVISIBLE_PATTERNS", [])
    def test_simple_view_empty_invisible_elements(self):
        """
        Test that empty SIMPLE_VIEW_INVISIBLE_ELEMENTS does not exclude anything.
        """
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvafpscounter", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        simple_view = graph.to_simple_view()

        # gvafpscounter should be visible (matches gva* pattern, no exclusion)
        expected_node_types = ["filesrc", "gvafpscounter", "fakesink"]
        actual_node_types = [node.type for node in simple_view.nodes]

        self.assertEqual(actual_node_types, expected_node_types)

    @patch("graph.SIMPLE_VIEW_INVISIBLE_ELEMENTS", "gvafpscounter")
    def test_simple_view_invisible_single_element(self):
        """
        Test exclusion of a single specific element type.
        """
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="gvafpscounter", data={}),
                Node(id="2", type="gvadetect", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )

        simple_view = graph.to_simple_view()

        # Only gvafpscounter should be hidden, gvadetect should remain
        expected_node_types = ["filesrc", "gvadetect", "fakesink"]
        actual_node_types = [node.type for node in simple_view.nodes]

        self.assertEqual(actual_node_types, expected_node_types)


class TestApplySimpleViewChanges(unittest.TestCase):
    """
    Test the apply_simple_view_changes method which merges property changes
    from the simple view back into the advanced view.
    """

    def test_positive_cases(self):
        """
        Test successful application of property changes from simple view to advanced view.

        This test verifies that:
        - Property modifications in simple view are correctly applied to advanced view
        - Hidden nodes in advanced view remain unchanged
        - Node IDs and structure are preserved
        - Multiple property changes work correctly
        - Adding and removing properties works
        """
        self.maxDiff = None

        for tc in apply_simple_view_changes_positive_test_cases:
            with self.subTest(test=tc.pipeline_description):
                result = Graph.apply_simple_view_changes(
                    modified_simple=tc.modified_pipeline_graph_simple,
                    original_simple=tc.original_pipeline_graph_simple,
                    original_advanced=tc.original_pipeline_graph,
                )

                # Verify that the result matches the expected graph
                self.assertEqual(
                    len(result.nodes), len(tc.modified_pipeline_graph.nodes)
                )

                # Check each node
                for i, (actual_node, expected_node) in enumerate(
                    zip(result.nodes, tc.modified_pipeline_graph.nodes)
                ):
                    self.assertEqual(
                        actual_node.id,
                        expected_node.id,
                        f"Node {i} ID mismatch: expected {expected_node.id}, got {actual_node.id}",
                    )
                    self.assertEqual(
                        actual_node.type,
                        expected_node.type,
                        f"Node {i} type mismatch: expected {expected_node.type}, got {actual_node.type}",
                    )
                    self.assertDictEqual(
                        actual_node.data,
                        expected_node.data,
                        f"Node {i} data mismatch: expected {expected_node.data}, got {actual_node.data}",
                    )

                # Verify edges remain unchanged
                self.assertEqual(
                    len(result.edges), len(tc.modified_pipeline_graph.edges)
                )
                for i, (actual_edge, expected_edge) in enumerate(
                    zip(result.edges, tc.modified_pipeline_graph.edges)
                ):
                    self.assertEqual(actual_edge.id, expected_edge.id)
                    self.assertEqual(actual_edge.source, expected_edge.source)
                    self.assertEqual(actual_edge.target, expected_edge.target)

    def test_negative_cases(self):
        """
        Test that unsupported operations raise appropriate ValueError exceptions.

        This test verifies that:
        - Adding edges raises ValueError with clear message
        - Removing edges raises ValueError with clear message
        - Modifying edge source/target raises ValueError with clear message
        - Adding nodes raises ValueError with clear message
        - Removing nodes raises ValueError with clear message
        - Changing node type raises ValueError with clear message
        - Error messages contain specific details about what changed
        """
        self.maxDiff = None

        for tc in apply_simple_view_changes_negative_test_cases:
            with self.subTest(test=tc.test_name):
                with self.assertRaises(ValueError) as cm:
                    Graph.apply_simple_view_changes(
                        modified_simple=tc.modified_pipeline_graph_simple,
                        original_simple=tc.original_pipeline_graph_simple,
                        original_advanced=tc.original_pipeline_graph,
                    )

                # Verify error message contains expected text
                self.assertIn(
                    tc.expected_error_message,
                    str(cm.exception),
                    f"Error message should contain '{tc.expected_error_message}', but got: {str(cm.exception)}",
                )

    def test_does_not_modify_input_graphs(self):
        """
        Test that apply_simple_view_changes does not modify the input graphs.

        This ensures that the method creates a deep copy and works on that copy,
        leaving the original graphs unchanged.
        """
        # Create test graphs
        original_advanced = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(id="2", type="gvadetect", data={"model": "yolo", "device": "GPU"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )

        original_simple = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="2", type="gvadetect", data={"model": "yolo", "device": "GPU"}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
                Edge(id="1", source="2", target="3"),
            ],
        )

        modified_simple = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="2", type="gvadetect", data={"model": "yolo", "device": "CPU"}
                ),  # Changed
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="2"),
                Edge(id="1", source="2", target="3"),
            ],
        )

        # Store original values for comparison
        original_advanced_node_2_device = original_advanced.nodes[2].data["device"]

        # Apply changes
        result = Graph.apply_simple_view_changes(
            modified_simple=modified_simple,
            original_simple=original_simple,
            original_advanced=original_advanced,
        )

        # Verify original_advanced was not modified
        self.assertEqual(
            original_advanced.nodes[2].data["device"],
            original_advanced_node_2_device,
            "Original advanced graph should not be modified",
        )

        # Verify result has the changed value
        self.assertEqual(
            result.nodes[2].data["device"],
            "CPU",
            "Result graph should have the modified value",
        )


class TestApplyLoopingModifications(unittest.TestCase):
    """Test cases for Graph.apply_looping_modifications method."""

    @patch("os.path.isfile", return_value=True)
    @patch("graph.VideosManager")
    def test_filesrc_replaced_with_multifilesrc(self, mock_videos_cls, mock_isfile):
        """Test that filesrc is replaced with multifilesrc loop=true."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mp4"}),
                Node(id="1", type="decodebin3", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        result = graph.apply_looping_modifications()

        # Check filesrc is replaced with multifilesrc
        self.assertEqual(result.nodes[0].type, "multifilesrc")
        self.assertEqual(result.nodes[0].data["loop"], "true")
        # Location should be just filename (basename of ts_path)
        self.assertEqual(result.nodes[0].data["location"], "video.ts")

    @patch("os.path.isfile", return_value=True)
    @patch("graph.VideosManager")
    def test_qtdemux_replaced_with_tsdemux(self, mock_videos_cls, mock_isfile):
        """Test that qtdemux is replaced with tsdemux."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mp4"}),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="h264parse", data={}),
                Node(id="3", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                Edge(id="2", source="2", target="3"),
            ],
        )

        result = graph.apply_looping_modifications()

        self.assertEqual(result.nodes[1].type, "tsdemux")

    @patch("os.path.isfile", return_value=True)
    @patch("graph.VideosManager")
    def test_matroskademux_replaced_with_tsdemux(self, mock_videos_cls, mock_isfile):
        """Test that matroskademux is replaced with tsdemux."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mkv"}),
                Node(id="1", type="matroskademux", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        result = graph.apply_looping_modifications()

        self.assertEqual(result.nodes[1].type, "tsdemux")

    @patch("os.path.isfile", return_value=True)
    @patch("graph.VideosManager")
    def test_avidemux_replaced_with_tsdemux(self, mock_videos_cls, mock_isfile):
        """Test that avidemux is replaced with tsdemux."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.avi"}),
                Node(id="1", type="avidemux", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        result = graph.apply_looping_modifications()

        self.assertEqual(result.nodes[1].type, "tsdemux")

    @patch("os.path.isfile", return_value=True)
    @patch("graph.VideosManager")
    def test_splitmuxsink_replaced_with_appsink(self, mock_videos_cls, mock_isfile):
        """Test that splitmuxsink is replaced with fakesink."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mp4"}),
                Node(id="1", type="qtdemux", data={}),
                Node(
                    id="2",
                    type="splitmuxsink",
                    data={"location": "/output/file_%02d.mp4", "max-size-time": "10"},
                ),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        result = graph.apply_looping_modifications()

        # Check splitmuxsink is replaced with fakesink
        self.assertEqual(result.nodes[2].type, "fakesink")
        # Check old properties are cleared
        self.assertNotIn("location", result.nodes[2].data)
        self.assertNotIn("max-size-time", result.nodes[2].data)

    @patch("os.path.isfile", return_value=True)
    @patch("graph.VideosManager")
    def test_original_graph_not_modified(self, mock_videos_cls, mock_isfile):
        """Test that apply_looping_modifications creates a deep copy."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance

        original_graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mp4"}),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        # Store original values
        original_type = original_graph.nodes[0].type
        original_location = original_graph.nodes[0].data.get("location")

        # Apply modifications
        result = original_graph.apply_looping_modifications()

        # Verify original is unchanged
        self.assertEqual(original_graph.nodes[0].type, original_type)
        self.assertEqual(
            original_graph.nodes[0].data.get("location"), original_location
        )
        self.assertNotIn("loop", original_graph.nodes[0].data)

        # Verify result is modified
        self.assertEqual(result.nodes[0].type, "multifilesrc")
        self.assertEqual(result.nodes[0].data["loop"], "true")

    @patch("graph.VideosManager")
    def test_ts_path_not_found_raises_error(self, mock_videos_cls):
        """Test that ValueError is raised when get_ts_path returns None."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = None
        mock_videos_cls.return_value = mock_videos_instance

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.xyz"}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
            ],
        )

        with self.assertRaises(ValueError) as cm:
            graph.apply_looping_modifications()

        self.assertIn("Cannot get TS path", str(cm.exception))

    @patch("graph.VideosManager")
    @patch("os.path.isfile")
    def test_ts_file_created_when_not_exists(self, mock_isfile, mock_videos_cls):
        """Test that TS file is created when it does not exist on disk."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_instance.get_video_path.return_value = "/videos/input/video.mp4"
        mock_videos_instance.ensure_ts_file.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance
        # First call (checking if ts exists) returns False, subsequent calls return True
        mock_isfile.side_effect = [False, True]

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mp4"}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
            ],
        )

        result = graph.apply_looping_modifications()

        # Verify ensure_ts_file was called
        mock_videos_instance.ensure_ts_file.assert_called_once()
        self.assertEqual(result.nodes[0].data["location"], "video.ts")

    @patch("graph.VideosManager")
    @patch("os.path.isfile")
    def test_ts_conversion_failure_raises_error(self, mock_isfile, mock_videos_cls):
        """Test that ValueError is raised when TS conversion fails."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_instance.get_video_path.return_value = "/videos/input/video.mp4"
        mock_videos_instance.ensure_ts_file.return_value = None  # Conversion failed
        mock_videos_cls.return_value = mock_videos_instance
        mock_isfile.return_value = False

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mp4"}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
            ],
        )

        with self.assertRaises(ValueError) as cm:
            graph.apply_looping_modifications()

        self.assertIn("Failed to create TS file", str(cm.exception))

    @patch("graph.VideosManager")
    @patch("os.path.isfile")
    def test_source_video_not_found_raises_error(self, mock_isfile, mock_videos_cls):
        """Test that ValueError is raised when source video cannot be found."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_instance.get_video_path.return_value = None  # Source not found
        mock_videos_cls.return_value = mock_videos_instance
        mock_isfile.return_value = False

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mp4"}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
            ],
        )

        with self.assertRaises(ValueError) as cm:
            graph.apply_looping_modifications()

        self.assertIn("Cannot find source video", str(cm.exception))

    @patch("graph.VideosManager")
    @patch("os.path.isfile")
    def test_multiple_modifications_in_complex_pipeline(
        self, mock_isfile, mock_videos_cls
    ):
        """Test looping modifications in a complex pipeline with tee."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance
        mock_isfile.return_value = True  # TS file exists

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.mp4"}),
                Node(id="1", type="qtdemux", data={}),
                Node(id="2", type="h264parse", data={}),
                Node(id="3", type="tee", data={"name": "t0"}),
                Node(id="4", type="queue", data={}),
                Node(
                    id="5",
                    type="splitmuxsink",
                    data={"location": "/output/file.mp4"},
                ),
                Node(id="6", type="queue", data={}),
                Node(id="7", type="gvadetect", data={"model": "yolo"}),
                Node(id="8", type="fakesink", data={}),
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
            ],
        )

        result = graph.apply_looping_modifications()

        # Check filesrc -> multifilesrc
        self.assertEqual(result.nodes[0].type, "multifilesrc")
        self.assertEqual(result.nodes[0].data["loop"], "true")
        self.assertEqual(result.nodes[0].data["location"], "video.ts")

        # Check qtdemux -> tsdemux
        self.assertEqual(result.nodes[1].type, "tsdemux")

        # Check splitmuxsink -> fakesink
        self.assertEqual(result.nodes[5].type, "fakesink")

        # Check other nodes are unchanged
        self.assertEqual(result.nodes[3].type, "tee")
        self.assertEqual(result.nodes[7].type, "gvadetect")
        self.assertEqual(result.nodes[8].type, "fakesink")

    @patch("graph.VideosManager")
    def test_filesrc_without_location(self, mock_videos_cls):
        """Test filesrc without location property is still modified."""
        mock_videos_instance = MagicMock()
        mock_videos_cls.return_value = mock_videos_instance

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={}),
                Node(id="1", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
            ],
        )

        result = graph.apply_looping_modifications()

        # Type should be changed to multifilesrc
        self.assertEqual(result.nodes[0].type, "multifilesrc")
        self.assertEqual(result.nodes[0].data["loop"], "true")
        # No location to modify
        self.assertNotIn("location", result.nodes[0].data)
        # get_ts_path should not be called
        mock_videos_instance.get_ts_path.assert_not_called()

    @patch("os.path.isfile", return_value=True)
    @patch("graph.VideosManager")
    def test_flvdemux_replaced_with_tsdemux(self, mock_videos_cls, mock_isfile):
        """Test that flvdemux is replaced with tsdemux."""
        mock_videos_instance = MagicMock()
        mock_videos_instance.get_ts_path.return_value = "/videos/input/video.ts"
        mock_videos_cls.return_value = mock_videos_instance

        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "video.flv"}),
                Node(id="1", type="flvdemux", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        result = graph.apply_looping_modifications()

        self.assertEqual(result.nodes[1].type, "tsdemux")


class TestUnifyModelInstanceIds(unittest.TestCase):
    """Test cases for Graph.unify_model_instance_ids method."""

    def test_same_device_and_model_get_same_instance_id(self):
        """Test that nodes with identical device and model get the same model-instance-id."""
        graph = Graph(
            nodes=[
                Node(
                    id="0",
                    type="gvadetect",
                    data={
                        "device": "GPU",
                        "model": "yolov8_detector",
                        "model-proc": "yolov8.json",
                    },
                ),
                Node(
                    id="1",
                    type="gvadetect",
                    data={
                        "device": "GPU",
                        "model": "yolov8_detector",
                        "model-proc": "different.json",
                    },
                ),
            ],
            edges=[],
        )

        result = graph.unify_model_instance_ids()

        # Both nodes should have the same model-instance-id
        self.assertEqual(
            result.nodes[0].data["model-instance-id"],
            result.nodes[1].data["model-instance-id"],
        )
        self.assertEqual(
            result.nodes[0].data["model-instance-id"], "gpu_yolov8_detector"
        )

    def test_different_device_get_different_instance_id(self):
        """Test that nodes with different devices get different model-instance-ids."""
        graph = Graph(
            nodes=[
                Node(
                    id="0",
                    type="gvadetect",
                    data={
                        "device": "GPU",
                        "model": "yolov8_detector",
                    },
                ),
                Node(
                    id="1",
                    type="gvadetect",
                    data={
                        "device": "CPU",
                        "model": "yolov8_detector",
                    },
                ),
            ],
            edges=[],
        )

        result = graph.unify_model_instance_ids()

        # Nodes should have different model-instance-ids
        self.assertNotEqual(
            result.nodes[0].data["model-instance-id"],
            result.nodes[1].data["model-instance-id"],
        )
        self.assertEqual(
            result.nodes[0].data["model-instance-id"], "gpu_yolov8_detector"
        )
        self.assertEqual(
            result.nodes[1].data["model-instance-id"], "cpu_yolov8_detector"
        )

    def test_different_model_get_different_instance_id(self):
        """Test that nodes with different models get different model-instance-ids."""
        graph = Graph(
            nodes=[
                Node(
                    id="0",
                    type="gvadetect",
                    data={
                        "device": "GPU",
                        "model": "yolov8_detector",
                    },
                ),
                Node(
                    id="1",
                    type="gvadetect",
                    data={
                        "device": "GPU",
                        "model": "resnet_classifier",
                    },
                ),
            ],
            edges=[],
        )

        result = graph.unify_model_instance_ids()

        # Nodes should have different model-instance-ids
        self.assertNotEqual(
            result.nodes[0].data["model-instance-id"],
            result.nodes[1].data["model-instance-id"],
        )
        self.assertEqual(
            result.nodes[0].data["model-instance-id"], "gpu_yolov8_detector"
        )
        self.assertEqual(
            result.nodes[1].data["model-instance-id"], "gpu_resnet_classifier"
        )

    def test_gvadetect_and_gvaclassify_with_same_params_get_same_id(self):
        """Test that gvadetect and gvaclassify with same device/model get same ID."""
        graph = Graph(
            nodes=[
                Node(
                    id="0",
                    type="gvadetect",
                    data={
                        "device": "GPU",
                        "model": "yolov8_detector",
                    },
                ),
                Node(
                    id="1",
                    type="gvaclassify",
                    data={
                        "device": "GPU",
                        "model": "yolov8_detector",
                    },
                ),
            ],
            edges=[],
        )

        result = graph.unify_model_instance_ids()

        # Both nodes should have the same model-instance-id
        self.assertEqual(
            result.nodes[0].data["model-instance-id"],
            result.nodes[1].data["model-instance-id"],
        )
        self.assertEqual(
            result.nodes[0].data["model-instance-id"], "gpu_yolov8_detector"
        )

    def test_other_node_types_not_modified(self):
        """Test that non-gva inference nodes are not modified."""
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="queue", data={}),
                Node(id="2", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
            ],
        )

        result = graph.unify_model_instance_ids()

        # None of these nodes should have model-instance-id
        for node in result.nodes:
            self.assertNotIn("model-instance-id", node.data)

    def test_empty_graph(self):
        """Test that empty graph is handled correctly."""
        graph = Graph(nodes=[], edges=[])

        result = graph.unify_model_instance_ids()

        self.assertEqual(len(result.nodes), 0)
        self.assertEqual(len(result.edges), 0)

    def test_nodes_without_device_or_model_properties(self):
        """Test that nodes missing device or model properties get sanitized IDs."""
        graph = Graph(
            nodes=[
                Node(id="0", type="gvadetect", data={}),
                Node(id="1", type="gvaclassify", data={"device": "GPU"}),
                Node(id="2", type="gvadetect", data={"model": "yolov8"}),
            ],
            edges=[],
        )

        result = graph.unify_model_instance_ids()

        # Node without any properties gets empty string combination
        self.assertEqual(result.nodes[0].data["model-instance-id"], "_")
        # Node with only device
        self.assertEqual(result.nodes[1].data["model-instance-id"], "gpu_")
        # Node with only model
        self.assertEqual(result.nodes[2].data["model-instance-id"], "_yolov8")

    def test_special_characters_sanitized(self):
        """Test that special characters in device and model are sanitized."""
        graph = Graph(
            nodes=[
                Node(
                    id="0",
                    type="gvadetect",
                    data={
                        "device": "GPU.0",
                        "model": "yolov8/detector@v1",
                    },
                ),
                Node(
                    id="1",
                    type="gvaclassify",
                    data={
                        "device": "NPU (Intel)",
                        "model": "model name with spaces",
                    },
                ),
            ],
            edges=[],
        )

        result = graph.unify_model_instance_ids()

        # Special characters should be replaced with underscores
        self.assertEqual(
            result.nodes[0].data["model-instance-id"], "gpu_0_yolov8_detector_v1"
        )
        self.assertEqual(
            result.nodes[1].data["model-instance-id"],
            "npu__intel__model_name_with_spaces",
        )

    def test_uppercase_converted_to_lowercase(self):
        """Test that uppercase characters are converted to lowercase."""
        graph = Graph(
            nodes=[
                Node(
                    id="0",
                    type="gvadetect",
                    data={
                        "device": "GPU",
                        "model": "YOLOv8_Detector",
                    },
                ),
            ],
            edges=[],
        )

        result = graph.unify_model_instance_ids()

        # All characters should be lowercase
        self.assertEqual(
            result.nodes[0].data["model-instance-id"], "gpu_yolov8_detector"
        )
        self.assertTrue(result.nodes[0].data["model-instance-id"].islower())

    def test_original_graph_not_modified(self):
        """Test that the original graph is not modified (deep copy is used)."""
        original_graph = Graph(
            nodes=[
                Node(
                    id="0",
                    type="gvadetect",
                    data={
                        "device": "GPU",
                        "model": "yolov8_detector",
                    },
                ),
            ],
            edges=[],
        )

        result = original_graph.unify_model_instance_ids()

        # Original graph should not have model-instance-id
        self.assertNotIn("model-instance-id", original_graph.nodes[0].data)
        # Result graph should have model-instance-id
        self.assertIn("model-instance-id", result.nodes[0].data)

    def test_multiple_nodes_complex_scenario(self):
        """Test a complex scenario with multiple nodes of different types."""
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(
                    id="1",
                    type="gvadetect",
                    data={"device": "GPU", "model": "yolov8_detector"},
                ),
                Node(id="2", type="queue", data={}),
                Node(
                    id="3",
                    type="gvaclassify",
                    data={"device": "GPU", "model": "resnet_classifier"},
                ),
                Node(
                    id="4",
                    type="gvadetect",
                    data={"device": "GPU", "model": "yolov8_detector"},
                ),
                Node(
                    id="5",
                    type="gvaclassify",
                    data={"device": "CPU", "model": "resnet_classifier"},
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
        )

        result = graph.unify_model_instance_ids()

        # Non-gva nodes should not have model-instance-id
        self.assertNotIn("model-instance-id", result.nodes[0].data)
        self.assertNotIn("model-instance-id", result.nodes[2].data)
        self.assertNotIn("model-instance-id", result.nodes[6].data)

        # Nodes 1 and 4 have same device and model -> same ID
        self.assertEqual(
            result.nodes[1].data["model-instance-id"],
            result.nodes[4].data["model-instance-id"],
        )
        self.assertEqual(
            result.nodes[1].data["model-instance-id"], "gpu_yolov8_detector"
        )

        # Node 3 has different model -> different ID
        self.assertEqual(
            result.nodes[3].data["model-instance-id"], "gpu_resnet_classifier"
        )

        # Node 5 has different device -> different ID from node 3
        self.assertNotEqual(
            result.nodes[3].data["model-instance-id"],
            result.nodes[5].data["model-instance-id"],
        )
        self.assertEqual(
            result.nodes[5].data["model-instance-id"], "cpu_resnet_classifier"
        )

    def test_full_pipeline_build_with_multiple_tee_branches_and_model_sharing(self):
        """Test that model-instance-ids are correctly unified across multiple tee branches.

        This test simulates a complex scenario where:
        - Pipeline has multiple tee branches
        - The same models are used across different branches
        - Model instance IDs should be unified when device and model match
        """
        graph = Graph(
            nodes=[
                Node(id="0", type="filesrc", data={"location": "test.mp4"}),
                Node(id="1", type="decodebin3", data={}),
                Node(id="2", type="tee", data={"name": "t"}),
                # Branch 1: GPU yolov8 -> GPU resnet
                Node(id="3", type="queue", data={}),
                Node(
                    id="4",
                    type="gvadetect",
                    data={"device": "GPU", "model": "yolov8_detector"},
                ),
                Node(
                    id="5",
                    type="gvaclassify",
                    data={"device": "GPU", "model": "resnet_classifier"},
                ),
                Node(id="6", type="fakesink", data={}),
                # Branch 2: GPU yolov8 -> CPU resnet
                Node(id="7", type="queue", data={}),
                Node(
                    id="8",
                    type="gvadetect",
                    data={"device": "GPU", "model": "yolov8_detector"},
                ),
                Node(
                    id="9",
                    type="gvaclassify",
                    data={"device": "CPU", "model": "resnet_classifier"},
                ),
                Node(id="10", type="fakesink", data={}),
                # Branch 3: CPU mobilenet
                Node(id="11", type="queue", data={}),
                Node(
                    id="12",
                    type="gvadetect",
                    data={"device": "CPU", "model": "mobilenet_detector"},
                ),
                Node(id="13", type="fakesink", data={}),
            ],
            edges=[
                Edge(id="0", source="0", target="1"),
                Edge(id="1", source="1", target="2"),
                # Branch 1
                Edge(id="2", source="2", target="3"),
                Edge(id="3", source="3", target="4"),
                Edge(id="4", source="4", target="5"),
                Edge(id="5", source="5", target="6"),
                # Branch 2
                Edge(id="6", source="2", target="7"),
                Edge(id="7", source="7", target="8"),
                Edge(id="8", source="8", target="9"),
                Edge(id="9", source="9", target="10"),
                # Branch 3
                Edge(id="10", source="2", target="11"),
                Edge(id="11", source="11", target="12"),
                Edge(id="12", source="12", target="13"),
            ],
        )

        result = graph.unify_model_instance_ids()

        # Verify non-inference nodes don't have model-instance-id
        for node_id in ["0", "1", "2", "3", "6", "7", "10", "11", "13"]:
            node = next(n for n in result.nodes if n.id == node_id)
            self.assertNotIn("model-instance-id", node.data)

        # Get inference nodes
        detect_gpu_yolov8_branch1 = next(n for n in result.nodes if n.id == "4")
        classify_gpu_resnet_branch1 = next(n for n in result.nodes if n.id == "5")
        detect_gpu_yolov8_branch2 = next(n for n in result.nodes if n.id == "8")
        classify_cpu_resnet_branch2 = next(n for n in result.nodes if n.id == "9")
        detect_cpu_mobilenet_branch3 = next(n for n in result.nodes if n.id == "12")

        # Verify that GPU yolov8 detectors in branch1 and branch2 share the same instance ID
        self.assertEqual(
            detect_gpu_yolov8_branch1.data["model-instance-id"],
            detect_gpu_yolov8_branch2.data["model-instance-id"],
        )
        self.assertEqual(
            detect_gpu_yolov8_branch1.data["model-instance-id"],
            "gpu_yolov8_detector",
        )

        # Verify GPU resnet classifier has correct ID
        self.assertEqual(
            classify_gpu_resnet_branch1.data["model-instance-id"],
            "gpu_resnet_classifier",
        )

        # Verify CPU resnet classifier has different ID from GPU version
        self.assertEqual(
            classify_cpu_resnet_branch2.data["model-instance-id"],
            "cpu_resnet_classifier",
        )
        self.assertNotEqual(
            classify_gpu_resnet_branch1.data["model-instance-id"],
            classify_cpu_resnet_branch2.data["model-instance-id"],
        )

        # Verify CPU mobilenet has unique ID
        self.assertEqual(
            detect_cpu_mobilenet_branch3.data["model-instance-id"],
            "cpu_mobilenet_detector",
        )

        # Verify all IDs are unique except for the shared GPU yolov8
        all_instance_ids = [
            detect_gpu_yolov8_branch1.data["model-instance-id"],
            classify_gpu_resnet_branch1.data["model-instance-id"],
            detect_gpu_yolov8_branch2.data["model-instance-id"],
            classify_cpu_resnet_branch2.data["model-instance-id"],
            detect_cpu_mobilenet_branch3.data["model-instance-id"],
        ]
        unique_ids = set(all_instance_ids)
        # Should have 4 unique IDs (GPU yolov8 is shared, so counted once)
        self.assertEqual(len(unique_ids), 4)


if __name__ == "__main__":
    unittest.main()
