# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import platform_paths
from graph import Graph, Node, _input_video_name_to_path, _build_chain
from gst_properties import quote_property, unquote_property, split_pipeline
from models import SupportedModel, SupportedModelsManager
from resources import DirectoryResourceManager
from videos import VideosManager


BACKEND_DIR = Path(__file__).resolve().parents[2]
PATH_DEFAULTS = {
    "MODELS_PATH": ("models/output", "/models/output"),
    "LABELS_PATH": ("labels", "/home/dlstreamer/dlstreamer/samples/labels"),
    "SCRIPTS_PATH": ("scripts", "/scripts"),
    "PUBLIC_MODEL_PROC_PATH": (
        "model-proc/public",
        platform_paths.LEGACY_PUBLIC_MODEL_PROC,
    ),
    "UPLOADED_IMAGES_DIR": ("images/input/uploaded", "/images/input/uploaded"),
    "AUTO_VIDEO_DIR": ("videos/input/auto", "/videos/input/auto"),
    "UPLOADED_VIDEO_DIR": ("videos/input/uploaded", "/videos/input/uploaded"),
    "OUTPUT_VIDEO_DIR": ("videos/output", "/videos/output"),
    "DEFAULT_RECORDINGS_FILE": (
        "videos/default_recordings.yaml",
        "/videos/default_recordings.yaml",
    ),
    "METADATA_DIR": ("metadata", "/metadata"),
}


class TestPortablePathDefaults(unittest.TestCase):
    def read_config(
        self, windows: bool, overrides: dict[str, str], root: str
    ) -> dict[str, str]:
        env = os.environ.copy()
        for key in (*PATH_DEFAULTS, "DATABASE_URL"):
            env.pop(key, None)
        env.update(overrides)
        env["LOCALAPPDATA"] = root
        code = (
            "import json, platform_paths\n"
            f"platform_paths.IS_WINDOWS = {windows!r}\n"
            "import database, images, models, resources, videos\n"
            "from managers import metadata_manager\n"
            "from api.routes import timeseries\n"
            "config = {}\n"
            "for module in (database, images, models, resources, videos, metadata_manager):\n"
            "    config.update({key: value for key, value in vars(module).items() "
            "if key.isupper() and isinstance(value, str)})\n"
            "config['TIMESERIES_METADATA_DIR'] = timeseries.METADATA_DIR\n"
            "print(json.dumps(config))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return json.loads(result.stdout)

    def test_platform_defaults_and_unchanged_in_memory_database(self):
        with tempfile.TemporaryDirectory(prefix="vippet data ") as root:
            for windows in (False, True):
                config = self.read_config(windows, {}, root)
                for key, (relative, posix) in PATH_DEFAULTS.items():
                    expected = (
                        str(Path(root) / "Vippet" / relative)
                        if windows
                        else (
                            posix
                            if key in {"MODELS_PATH", "DEFAULT_RECORDINGS_FILE"}
                            else os.path.normpath(posix)
                        )
                    )
                    with self.subTest(windows=windows, key=key):
                        self.assertEqual(config[key], expected)
                self.assertEqual(config["DATABASE_URL"], "sqlite+aiosqlite:///:memory:")
                self.assertEqual(
                    config["TIMESERIES_METADATA_DIR"], config["METADATA_DIR"]
                )

    def test_environment_overrides_win_on_both_platforms(self):
        with tempfile.TemporaryDirectory(prefix="custom data ") as root:
            overrides = {key: str(Path(root) / key.lower()) for key in PATH_DEFAULTS}
            overrides["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
            for windows in (False, True):
                config = self.read_config(windows, overrides, root)
                for key, expected in overrides.items():
                    with self.subTest(windows=windows, key=key):
                        self.assertEqual(config[key], expected)
                self.assertEqual(
                    config["TIMESERIES_METADATA_DIR"], overrides["METADATA_DIR"]
                )

    def test_windows_default_without_localappdata(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(platform_paths, "IS_WINDOWS", True),
            patch.dict(os.environ),
            patch.object(platform_paths.Path, "home", return_value=Path(root)),
        ):
            os.environ.pop("LOCALAPPDATA", None)
            self.assertEqual(
                platform_paths.data_path("models/output", "/models/output"),
                str(Path(root) / "AppData/Local/Vippet/models/output"),
            )


class TestPortableProperties(unittest.TestCase):
    def test_quoted_properties_round_trip(self):
        for value in (
            r"C:\video files\clip.mp4",
            r"\\server\share\clip.mp4",
            'C:/video files/a!"b.mp4',
            "C:/video's/clip.mp4",
            "C:\\video files\\",
            "",
            "/simple/clip.mp4",
        ):
            with self.subTest(value=value):
                self.assertEqual(unquote_property(quote_property(value)), value)
                nodes = {"0": Node("0", "filesink", {"location": value})}
                parts = []
                _build_chain("0", nodes, {}, {}, set(), parts)
                graph = Graph.from_pipeline_description(" ".join(parts))
                self.assertEqual(graph.nodes[0].data["location"], value)

    def test_pipeline_separators_and_unterminated_quotes(self):
        self.assertEqual(
            split_pipeline('filesrc location="a ! b.mp4" ! fakesink'),
            ['filesrc location="a ! b.mp4" ', " fakesink"],
        )
        with self.assertRaisesRegex(ValueError, "Unterminated"):
            split_pipeline('filesrc location="unfinished')

    def test_native_absolute_source_bypasses_video_lookup(self):
        with tempfile.TemporaryDirectory(prefix="video paths ") as root:
            path = str(Path(root) / "clip.mp4")
            for kind in ("filesrc", "multifilesrc"):
                with self.subTest(kind=kind), patch("graph.VideosManager") as manager:
                    nodes = [Node("0", kind, {"location": path})]
                    _input_video_name_to_path(nodes)
                    manager.assert_not_called()
                    self.assertEqual(nodes[0].data["location"], path)

    def test_null_output_uses_native_device(self):
        graph = Graph.from_pipeline_description("gvametapublish file-path=/dev/null")
        self.assertEqual(graph.nodes[0].data["file-path"], os.devnull)
        parts = []
        _build_chain(
            "0",
            {"0": Node("0", "gvametapublish", {"file-path": "/dev/null"})},
            {},
            {},
            set(),
            parts,
        )
        self.assertIn(f"file-path={quote_property(os.devnull)}", " ".join(parts))

    def test_ts_conversion_quotes_paths(self):
        with patch("videos.PipelineRunner") as runner:
            for extension in ("mp4", "264"):
                source = rf"C:\video files\clip!.{extension}"
                target = r"C:\video files\clip!.ts"
                with self.subTest(extension=extension):
                    self.assertTrue(
                        VideosManager._convert_to_ts(source, target, extension, "h264")
                    )
                    description = runner.return_value.run.call_args.args[0]
                    self.assertIn(f"location={quote_property(source)}", description)
                    self.assertIn(f"location={quote_property(target)}", description)


class TestLegacyResourceMapping(unittest.TestCase):
    def test_mapping_is_windows_only_and_preserves_custom_paths(self):
        legacy = platform_paths.LEGACY_PUBLIC_MODEL_PROC + "/preproc.json"
        with tempfile.TemporaryDirectory() as root:
            for windows in (False, True):
                with patch.object(platform_paths, "IS_WINDOWS", windows):
                    self.assertEqual(
                        platform_paths.resolve_legacy_path(
                            legacy, platform_paths.LEGACY_PUBLIC_MODEL_PROC, root
                        ),
                        str(Path(root) / "preproc.json") if windows else legacy,
                    )
                    for value in (
                        "/custom/proc.json",
                        r"C:\custom\proc.json",
                        "model/proc.json",
                    ):
                        with self.subTest(windows=windows, value=value):
                            self.assertEqual(
                                platform_paths.resolve_legacy_path(
                                    value, platform_paths.LEGACY_PUBLIC_MODEL_PROC, root
                                ),
                                value,
                            )

    def test_mapping_rejects_traversal_and_windows_path_escapes(self):
        with patch.object(platform_paths, "IS_WINDOWS", True):
            for suffix in (
                "../secret.xml",
                "model/../../secret.xml",
                r"..\secret.xml",
                "/secret.xml",
                "C:secret.xml",
                "file.xml:stream",
                "file\0.xml",
            ):
                with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                    platform_paths.resolve_legacy_path(
                        "/models/output/" + suffix, "/models/output", "models"
                    )

    def test_mapping_rejects_symlink_outside_configured_root(self):
        if sys.platform == "win32":
            self.skipTest("Creating symlinks may require Windows developer privileges")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "models"
            root.mkdir()
            outside = Path(directory) / "outside"
            outside.mkdir()
            (root / "link").symlink_to(outside, target_is_directory=True)
            with (
                patch.object(platform_paths, "IS_WINDOWS", True),
                self.assertRaises(ValueError),
            ):
                platform_paths.resolve_legacy_path(
                    "/models/output/link/model.xml", "/models/output", str(root)
                )

    def test_model_proc_mapping_does_not_change_stored_reference(self):
        legacy = platform_paths.LEGACY_PUBLIC_MODEL_PROC + "/preproc.json"
        with (
            tempfile.TemporaryDirectory(prefix="public proc ") as root,
            patch.object(platform_paths, "IS_WINDOWS", True),
            patch("models.PUBLIC_MODEL_PROC_PATH", root),
            patch.object(SupportedModelsManager, "_instance", None),
        ):
            model = SupportedModel(
                "test",
                "Test",
                "public",
                "classification",
                "model.xml",
                model_proc=legacy,
            )
            self.assertEqual(model.model_proc, legacy)
            self.assertEqual(model.model_proc_full, str(Path(root) / "preproc.json"))
            full_path_model = SupportedModel(
                "test",
                "Test",
                "public",
                "classification",
                "model.xml",
                model_proc=legacy,
                model_proc_is_full_path=True,
            )
            self.assertEqual(full_path_model.model_proc_full, model.model_proc_full)
            SupportedModelsManager()._models = [model]
            graph = Graph.from_pipeline_description(
                f"gvaclassify model=model.xml model-proc={legacy}"
            )
            self.assertEqual(graph.nodes[0].data["model"], "Test")

    def test_nested_models_and_genai_lookup_use_configured_root(self):
        legacy = "/models/output/openvino_models/gpu/model"
        with (
            tempfile.TemporaryDirectory(prefix="model paths ") as root,
            patch.object(platform_paths, "IS_WINDOWS", True),
            patch("models.MODELS_PATH", root),
            patch.object(SupportedModelsManager, "_instance", None),
        ):
            model = SupportedModel(
                "vlm",
                "VLM",
                "public",
                "vision_language_models",
                "openvino_models/gpu/model",
            )
            SupportedModelsManager()._models = [model]
            graph = Graph.from_pipeline_description(f"gvagenai model-path={legacy}")
            self.assertEqual(graph.nodes[0].data["model"], "VLM")
            absolute = SupportedModel(
                "vlm", "VLM", "public", "vision_language_models", legacy
            )
            self.assertEqual(absolute.model_path_full, model.model_path_full)

    def test_labels_and_scripts_resolve_under_configured_directories(self):
        from graph import (
            _labels_path_to_display_name,
            _labels_name_to_path,
            _module_path_to_display_name,
            _module_name_to_path,
        )

        with tempfile.TemporaryDirectory(prefix="resources ") as root:
            manager = DirectoryResourceManager(root)
            for filename in ("classes.txt", "processing.py"):
                (Path(root) / filename).write_text("test", encoding="utf-8")
            labels = [
                Node(
                    "0",
                    "gvadetect",
                    {
                        "labels": "/home/dlstreamer/dlstreamer/samples/labels/classes.txt"
                    },
                )
            ]
            scripts = [Node("0", "gvapython", {"module": "/scripts/processing.py"})]
            with (
                patch("graph.labels_manager", manager),
                patch("graph.scripts_manager", manager),
            ):
                _labels_path_to_display_name(labels)
                _labels_name_to_path(labels)
                _module_path_to_display_name(scripts)
                _module_name_to_path(scripts)
            self.assertEqual(labels[0].data["labels"], str(Path(root) / "classes.txt"))
            self.assertEqual(
                scripts[0].data["module"], str(Path(root) / "processing.py")
            )


class TestPortableDownloadStaging(unittest.TestCase):
    def test_download_stages_in_destination_and_closes_file_before_move(self):
        with tempfile.TemporaryDirectory(prefix="video downloads ") as root:
            manager = object.__new__(VideosManager)
            response = MagicMock()
            response.__enter__.return_value = response
            response.status = 200
            response.read.side_effect = [b"video", b""]
            real_temp = tempfile.NamedTemporaryFile
            staged = []

            def create_temp(*args, **kwargs):
                handle = real_temp(*args, **kwargs)
                staged.append(handle)
                return handle

            def move(source, target):
                self.assertTrue(staged[0].closed)
                self.assertEqual(Path(source).parent, Path(root))
                self.assertEqual(Path(source).read_bytes(), b"video")
                os.replace(source, target)
                return True

            with (
                patch("videos.AUTO_VIDEO_DIR", root),
                patch(
                    "videos.urllib.request.urlopen", return_value=response
                ) as urlopen,
                patch("videos.tempfile.NamedTemporaryFile", side_effect=create_temp),
                patch.object(manager, "_move_file", side_effect=move),
            ):
                result = manager._download_video(
                    "https://example.invalid/video", "clip.mp4"
                )
            self.assertEqual(result, str(Path(root) / "clip.mp4"))
            assert result is not None
            self.assertEqual(Path(result).read_bytes(), b"video")
            self.assertEqual(list(Path(root).glob(".vippet-download-*")), [])
            self.assertEqual(urlopen.call_args.kwargs["timeout"], 600)

    def test_partial_download_and_failed_move_remove_temporary_file(self):
        with tempfile.TemporaryDirectory() as root:
            for fail_read in (False, True):
                with self.subTest(fail_read=fail_read):
                    response = MagicMock()
                    response.__enter__.return_value = response
                    response.status = 200
                    response.read.side_effect = (
                        [b"partial", OSError("read failed")]
                        if fail_read
                        else [b"video", b""]
                    )
                    manager = object.__new__(VideosManager)
                    with (
                        patch("videos.AUTO_VIDEO_DIR", root),
                        patch("videos.urllib.request.urlopen", return_value=response),
                        patch.object(manager, "_move_file", return_value=False),
                        patch("videos.logger") as logger,
                    ):
                        self.assertIsNone(
                            manager._download_video(
                                "https://example.invalid/video", "clip.mp4"
                            )
                        )
                        if fail_read:
                            logger.error.assert_called()
                    self.assertEqual(list(Path(root).iterdir()), [])
