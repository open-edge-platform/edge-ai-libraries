# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import hashlib
import io
import json
import os
import re
import tempfile
import unittest
import zipfile

import yaml

from app_export.archive import AppSource, app_name, write_app_archive
from app_export.pipelines import AppPipelines

MODEL_DIR = "/models/output/ultralytics/public/pallet_defect_detection/INT8"
SOURCE = AppSource(
    pipeline_id="defect-detection",
    pipeline_name="Defect Detection",
    variant_id="npu",
    variant_name="NPU",
    launch_string="filesrc location=/videos/input/auto/warehouse.avi ! fakesink",
)


class TestWriteAppArchive(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.roots = {
            "/models": os.path.join(self.tmp, "models"),
            "/videos": os.path.join(self.tmp, "videos"),
        }
        self._write(f"{MODEL_DIR}/pallet_defect_detection.xml", b"<net/>")
        self._write(f"{MODEL_DIR}/pallet_defect_detection.bin", b"\0" * 4096)
        self._write(f"{MODEL_DIR}/config.json", b"{}")
        self._write("/videos/input/auto/warehouse.avi", b"avi")
        self._write("/videos/input/auto/warehouse.ts", b"ts")

    def _write(self, container_path: str, content: bytes) -> str:
        root = "/" + container_path.split("/")[1]
        path = os.path.join(self.roots[root], container_path[len(root) + 1 :])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as file:
            file.write(content)
        return path

    def _app(self, devices: list[str], **files: list[str]) -> AppPipelines:
        return AppPipelines(
            launch_strings={"fakesink": "a", "file": "b", "rtsp": "c"},
            devices=devices,
            model_files=files.get(
                "model_files", [f"{MODEL_DIR}/pallet_defect_detection.xml"]
            ),
            video_files=files.get(
                "video_files",
                ["/videos/input/auto/warehouse.avi", "/videos/input/auto/warehouse.ts"],
            ),
        )

    def _archive(self, app: AppPipelines) -> zipfile.ZipFile:
        buffer = io.BytesIO()
        write_app_archive(buffer, SOURCE, app, self.roots)
        return zipfile.ZipFile(buffer)

    def test_layout(self):
        archive = self._archive(self._app(["NPU"]))
        root = app_name(SOURCE)
        self.assertEqual(root, "defect-detection-npu-app")

        names = set(archive.namelist())
        expected = {
            "compose.yml",
            "README.md",
            "pipelines.json",
            "manifest.json",
            "start_app.sh",
            "run.sh",
            "stop.sh",
            "status.sh",
            "stop_app.sh",
            "scripts/common.sh",
            "output/",
            f"assets{MODEL_DIR}/pallet_defect_detection.xml",
            f"assets{MODEL_DIR}/pallet_defect_detection.bin",
            f"assets{MODEL_DIR}/config.json",
            "assets/videos/input/auto/warehouse.avi",
            "assets/videos/input/auto/warehouse.ts",
        }
        self.assertEqual(names, {f"{root}/{name}" for name in expected})

        modes = {
            info.filename.removeprefix(f"{root}/"): (info.external_attr >> 16) & 0o777
            for info in archive.infolist()
        }
        self.assertEqual(modes["start_app.sh"], 0o755)
        self.assertEqual(modes["run.sh"], 0o755)
        self.assertEqual(modes["scripts/common.sh"], 0o644)
        self.assertEqual(
            archive.getinfo(
                f"{root}/assets{MODEL_DIR}/pallet_defect_detection.bin"
            ).compress_type,
            zipfile.ZIP_STORED,
        )

        self.assertEqual(
            json.loads(archive.read(f"{root}/pipelines.json")),
            {"fakesink": "a", "file": "b", "rtsp": "c"},
        )
        manifest = json.loads(archive.read(f"{root}/manifest.json"))
        self.assertEqual(manifest["pipeline"]["id"], "defect-detection")
        self.assertEqual(manifest["devices"], ["NPU"])
        for asset in manifest["assets"]:
            content = archive.read(f"{root}/{asset['path']}")
            self.assertEqual(asset["size"], len(content))
            self.assertEqual(asset["sha256"], hashlib.sha256(content).hexdigest())

        for name in ("compose.yml", "README.md"):
            self.assertIsNone(
                re.search(r"@[A-Z0-9_]+@", archive.read(f"{root}/{name}").decode()),
                name,
            )

    def test_compose_mounts_the_devices_of_the_variant(self):
        cases = {
            "CPU": None,
            "GPU": ["/dev/dri:/dev/dri"],
            "NPU": ["/dev/dri:/dev/dri", "/dev/accel:/dev/accel"],
        }
        for device, mounts in cases.items():
            with self.subTest(device=device):
                archive = self._archive(self._app([device]))
                compose = yaml.safe_load(
                    archive.read(f"{app_name(SOURCE)}/compose.yml")
                )
                server = compose["services"]["dlstreamer-pipeline-server"]
                self.assertEqual(server.get("devices"), mounts)
                self.assertEqual("group_add" in server, mounts is not None)
                self.assertEqual(
                    server["volumes"],
                    [
                        "./assets/models:/models:ro",
                        "./assets/videos:/videos:ro",
                        "./output:/output",
                    ],
                )

    def test_rejects_missing_files_and_paths_outside_the_roots(self):
        outside = os.path.join(self.tmp, "secret")
        with open(outside, "wb") as file:
            file.write(b"secret")
        os.symlink(outside, os.path.join(self.roots["/videos"], "input/auto/link.avi"))

        cases = {
            "missing video": (
                {"video_files": ["/videos/input/auto/missing.avi"]},
                "missing.avi is missing",
            ),
            "symlink out of the root": (
                {"video_files": ["/videos/input/auto/link.avi"]},
                "resolves outside /videos",
            ),
            "missing model directory": (
                {"model_files": ["/models/output/none/model.xml"]},
                "Model directory /models/output/none is missing",
            ),
        }
        for label, (files, message) in cases.items():
            with self.subTest(label):
                with self.assertRaisesRegex(ValueError, message):
                    self._archive(self._app(["CPU"], **files))


if __name__ == "__main__":
    unittest.main()
