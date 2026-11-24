# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import unittest
from unittest.mock import MagicMock, patch

from app_export.pipelines import build_app_pipelines, check_exportable
from graph import Graph

PDD_XML = "/models/output/ultralytics/public/pallet_defect_detection/INT8/pallet_defect_detection.xml"


def _model(name: str, path: str) -> MagicMock:
    model = MagicMock()
    model.name = name
    model.model_path_full = path
    model.model_proc_full = ""
    return model


_INSTALLED_MODELS = {
    "Pallet Defect Detection": _model("pallet_defect_detection", PDD_XML),
    "YOLO11s": _model("yolo11s", "/models/output/public/yolo11s/FP16/yolo11s.xml"),
}


def _pdd_graph(device: str = "CPU", **overrides: dict) -> Graph:
    """Return the Pallet Defect Detection graph as ViPPET stores it, optionally with node data overrides by id."""
    elements = [
        ("filesrc", {"location": "warehouse.avi"}),
        ("decodebin3", {}),
        (
            "gvadetect",
            {
                "model": "Pallet Defect Detection",
                "device": device,
                "pre-process-backend": "opencv" if device == "CPU" else "va",
            },
        ),
        ("queue", {}),
        ("gvawatermark", {}),
        ("gvametaconvert", {"add-empty-results": "true"}),
        ("queue", {}),
        (
            "gvametapublish",
            {"method": "file", "file-format": "json-lines", "file-path": "/dev/null"},
        ),
        ("gvafpscounter", {"starting-frame": "100"}),
        ("fakesink", {"name": "default_output_sink"}),
    ]
    nodes = []
    for index, (element, data) in enumerate(elements):
        node = {"id": str(index), "type": element, "data": dict(data)}
        node.update(overrides.get(str(index), {}))
        nodes.append(node)
    edges = [
        {"id": str(index), "source": str(index), "target": str(index + 1)}
        for index in range(len(nodes) - 1)
    ]
    return Graph.from_dict({"nodes": nodes, "edges": edges})


class AppPipelinesTestBase(unittest.TestCase):
    def setUp(self) -> None:
        models = MagicMock()
        models.find_installed_model_by_display_name.side_effect = _INSTALLED_MODELS.get
        models.is_model_supported_on_device.return_value = True

        videos = MagicMock()
        videos.get_video_path.side_effect = lambda name: f"/videos/input/auto/{name}"
        videos.get_ts_path.return_value = "/videos/input/auto/warehouse.ts"
        videos.get_video.return_value = MagicMock(codec="h264")

        self.decoder = MagicMock()
        self.decoder.is_bayer_format.return_value = False
        self.decoder.is_raw_format.return_value = False

        for target, value in (
            ("graph.SupportedModelsManager", models),
            ("app_export.pipelines.SupportedModelsManager", models),
            ("graph.VideosManager", videos),
            ("graph.VideoDecoder", self.decoder),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("graph.os.path.isfile", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestBuildAppPipelines(AppPipelinesTestBase):
    def test_cpu_variant(self):
        self.decoder.select_decoder.return_value = "avdec_h264"

        app = build_app_pipelines(_pdd_graph("CPU"))

        self.assertEqual(app.devices, ["CPU"])
        self.assertEqual(app.model_files, [PDD_XML])
        self.assertEqual(app.other_model_files, [])
        self.assertEqual(
            app.video_files,
            ["/videos/input/auto/warehouse.avi", "/videos/input/auto/warehouse.ts"],
        )

        fakesink = app.launch_strings["fakesink"]
        self.assertTrue(
            fakesink.startswith(
                "multifilesrc location=/videos/input/auto/warehouse.ts loop=true ! "
                "parsebin ! avdec_h264 ! video/x-raw ! gvadetect"
            ),
            fakesink,
        )
        self.assertIn(f"model={PDD_XML}", fakesink)
        self.assertIn("file-path=/output/{name}.jsonl", fakesink)
        self.assertNotIn("gvawatermark", fakesink)
        self.assertTrue(fakesink.endswith("fakesink name=default_output_sink"))

        file = app.launch_strings["file"]
        self.assertTrue(
            file.startswith("filesrc location=/videos/input/auto/warehouse.avi ! "),
            file,
        )
        self.assertIn("gvawatermark", file)
        self.assertTrue(
            file.endswith(
                "openh264enc bitrate=16000000 complexity=low ! h264parse ! mp4mux ! "
                "filesink location=/output/{name}.mp4"
            ),
            file,
        )

        rtsp = app.launch_strings["rtsp"]
        self.assertTrue(rtsp.startswith("multifilesrc "), rtsp)
        self.assertIn("openh264enc bitrate=16000000 complexity=low usage-type=", rtsp)
        self.assertTrue(
            rtsp.endswith(
                "h264parse ! rtspclientsink protocols=tcp "
                "location=rtsp://mediamtx:8554/{name}"
            ),
            rtsp,
        )

    def test_gpu_and_npu_variants_encode_with_vah264enc(self):
        self.decoder.select_decoder.return_value = "vah264dec"

        for device in ("GPU", "NPU"):
            with self.subTest(device=device):
                app = build_app_pipelines(_pdd_graph(device))

                self.assertEqual(app.devices, [device])
                self.assertIn(
                    "vah264dec ! video/x-raw(memory:VAMemory) ! gvadetect",
                    app.launch_strings["fakesink"],
                )
                self.assertIn(
                    "vah264enc ! h264parse ! mp4mux", app.launch_strings["file"]
                )
                self.assertIn(
                    "vah264enc bitrate=16000 target-usage=4 max-qp=30 ! h264parse ! "
                    "rtspclientsink",
                    app.launch_strings["rtsp"],
                )
                self.assertNotIn("vah264lpenc", " ".join(app.launch_strings.values()))

    def test_mqtt_publisher_writes_to_file(self):
        self.decoder.select_decoder.return_value = "avdec_h264"
        graph = _pdd_graph(
            "CPU",
            **{
                "7": {
                    "data": {
                        "method": "mqtt",
                        "address": "mqtt-broker:1883",
                        "topic": "pdd",
                        "mqtt-client-id": "pdd",
                        "mqtt-config": "/etc/mqtt.json",
                    }
                }
            },
        )

        app = build_app_pipelines(graph)

        for sink, launch_string in app.launch_strings.items():
            with self.subTest(sink=sink):
                self.assertIn(
                    "gvametapublish method=file file-format=json-lines "
                    "file-path=/output/{name}.jsonl ",
                    launch_string,
                )
                self.assertNotIn("mqtt", launch_string)
                self.assertNotIn("address=", launch_string)

    def test_rejects_files_outside_models_and_videos(self):
        self.decoder.select_decoder.return_value = "avdec_h264"
        graph = _pdd_graph("CPU")
        graph.nodes[2].data["labels"] = "coco.txt"

        with patch("graph.labels_manager") as labels:
            labels.get_path.return_value = "/labels/coco.txt"
            with self.assertRaisesRegex(ValueError, "labels=/labels/coco.txt"):
                build_app_pipelines(graph)


class TestCheckExportable(AppPipelinesTestBase):
    def test_accepts_pallet_defect_detection(self):
        check_exportable(_pdd_graph("GPU"))

    def test_rejects_unsupported_variants(self):
        cases = {
            "camera source": (
                {"0": {"type": "rtspsrc", "data": {"location": "rtsp://cam/1"}}},
                "rtspsrc \\(camera\\)",
            ),
            "VLM element": (
                {"3": {"type": "gvagenai", "data": {}}},
                "gvagenai",
            ),
            "ViPPET plugin": (
                {"3": {"type": "gvaproximitytrigger_py", "data": {}}},
                "gvaproximitytrigger_py",
            ),
            "extra file sink": (
                {"9": {"type": "filesink", "data": {"location": "/tmp/x.mp4"}}},
                "filesink",
            ),
            "other model": (
                {"2": {"data": {"model": "YOLO11s", "device": "CPU"}}},
                "Pallet Defect Detection pipelines only",
            ),
            "second GPU": (
                {
                    "2": {
                        "data": {"model": "Pallet Defect Detection", "device": "GPU.1"}
                    }
                },
                "first GPU only\\) and NPU; this variant uses GPU.1",
            ),
            "composite device": (
                {
                    "2": {
                        "data": {
                            "model": "Pallet Defect Detection",
                            "device": "HETERO:GPU,CPU",
                        }
                    }
                },
                "this variant uses HETERO:GPU,CPU",
            ),
            "missing model": (
                {"2": {"data": {"model": "Not Installed", "device": "CPU"}}},
                "'Not Installed' is not installed",
            ),
            "no inference": (
                {"2": {"type": "queue", "data": {}}},
                "Pallet Defect Detection pipelines only",
            ),
        }
        for label, (overrides, message) in cases.items():
            with self.subTest(label):
                with self.assertRaisesRegex(ValueError, message):
                    check_exportable(_pdd_graph("CPU", **overrides))


if __name__ == "__main__":
    unittest.main()
