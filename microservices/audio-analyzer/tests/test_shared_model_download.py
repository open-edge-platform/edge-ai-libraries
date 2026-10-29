# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import ensure_model
from utils.local_models import COMPLETION_FILE, get_local_model, model_directory
from utils.provision_models import record_snapshot


class SharedModelTests(unittest.TestCase):
    def test_openvino_exports_locally_downloaded_hf_snapshot(self):
        with tempfile.TemporaryDirectory() as base, \
             patch.object(ensure_model, "_whisper_ir_exists", side_effect=[False, True]), \
             patch.object(ensure_model, "get_local_model", return_value="/shared/whisper") as fetch, \
             patch.object(ensure_model, "run_cli", return_value=0) as run:
            success, _ = ensure_model._download_openvino_model("openai/whisper-base", base, None)
        self.assertTrue(success)
        fetch.assert_called_once_with(
            "openai/whisper-base", download_path="whisper-source",
            required_files=["config.json"],
        )
        self.assertEqual(run.call_args.kwargs["cmd"][run.call_args.kwargs["cmd"].index("--model") + 1], "/shared/whisper")
        self.assertEqual(
            run.call_args.kwargs["cmd"][run.call_args.kwargs["cmd"].index("--task") + 1],
            "automatic-speech-recognition-with-past",
        )

    def test_whisper_ir_rejects_decoder_without_beam_index(self):
        with tempfile.TemporaryDirectory() as base, \
             patch.object(ensure_model, "_ir_exists", return_value=True), \
             patch("openvino.Core") as core:
            core.return_value.read_model.return_value.inputs = [
                type("Port", (), {"get_names": lambda self: {"input_ids"}})()
            ]
            self.assertFalse(ensure_model._whisper_ir_exists(base))
            core.return_value.read_model.return_value.inputs = [
                type("Port", (), {"get_names": lambda self: {"beam_idx"}})()
            ]
            self.assertTrue(ensure_model._whisper_ir_exists(base))

    def test_whispercpp_uses_single_requested_file(self):
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as source:
            (Path(source) / "ggml-base.bin").write_bytes(b"weights")
            with patch.object(ensure_model, "get_local_model", return_value=source) as fetch:
                self.assertTrue(ensure_model._download_whispercpp_model("whisper-base", base))
            fetch.assert_called_once_with(
                "ggerganov/whisper.cpp", download_path="whisper-source",
                required_files=["ggml-base.bin"],
            )
            self.assertEqual((Path(base) / "ggml-base.bin").read_bytes(), b"weights")

    def test_openai_whisper_downloads_checkpoint_directly(self):
        with tempfile.TemporaryDirectory() as base, \
             patch.object(ensure_model.config.models.asr, "provider", "openai"), \
             patch.object(ensure_model.config.models.asr, "name", "whisper-base"), \
             patch.object(ensure_model, "get_asr_model_path", return_value=base), \
             patch("whisper._download") as download:
            checkpoint = Path(base) / "base.pt"
            checkpoint.write_bytes(b"weights")
            download.return_value = str(checkpoint)
            ensure_model.ensure_model()
            import whisper
            download.assert_called_once()
            self.assertEqual(download.call_args.args[0], whisper._MODELS["base"])
            self.assertEqual(download.call_args.args[1:], (base, False))
            self.assertEqual(Path(base, "base.pt").read_bytes(), b"weights")

    def test_pyannote_snapshot_is_local(self):
        with patch.object(ensure_model, "get_local_model", return_value="/shared/diar") as fetch:
            self.assertEqual(
                ensure_model._get_diarization_snapshot("pyannote/example", required_files=["config.yaml"]),
                "/shared/diar",
            )
        fetch.assert_called_once_with(
            "pyannote/example", download_path="diarization",
            required_files=["config.yaml"],
            models_base_path=ensure_model.config.models.diarization.models_base_path,
        )

    def test_cached_export_does_not_need_a_downloader(self):
        with patch.object(ensure_model, "_whisper_ir_exists", return_value=True), \
             patch.object(ensure_model, "get_local_model") as fetch, \
             tempfile.TemporaryDirectory() as base:
            self.assertEqual(
                ensure_model._download_openvino_model("openai/whisper-base", base, None),
                (True, base),
            )
            fetch.assert_not_called()


class LocalSnapshotTests(unittest.TestCase):
    def test_modelscope_snapshot_is_separate_from_huggingface(self):
        with tempfile.TemporaryDirectory() as base:
            directory = model_directory("iic/example", "funasr", base, hub="modelscope")
            self.assertEqual(directory, Path(base) / "funasr" / "modelscope" / "iic_example")
            directory.mkdir(parents=True)
            (directory / "model.pt").write_bytes(b"weights")
            record_snapshot("iic/example", "v2.0.4", directory)
            self.assertEqual(get_local_model(
                "iic/example", "v2.0.4", hub="modelscope",
                models_base_path=base, required_files=["model.pt"],
            ), str(directory))
            with self.assertRaisesRegex(RuntimeError, "provisioning job"):
                get_local_model("iic/example", "v2.0.4", models_base_path=base)

    def test_invalid_hub_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid model hub"):
            model_directory("iic/example", "funasr", "/tmp/models", hub="../escape")

    def test_valid_snapshot_loads_without_network(self):
        with tempfile.TemporaryDirectory() as base:
            directory = model_directory("funasr/example", "funasr", base)
            directory.mkdir(parents=True)
            (directory / "model.pt").write_bytes(b"weights")
            record_snapshot("funasr/example", "commit", directory)
            with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network call")):
                self.assertEqual(
                    get_local_model("funasr/example", "commit", models_base_path=base, required_files=["model.pt"]),
                    str(directory),
                )

    def test_missing_incomplete_or_wrong_revision_fails(self):
        with tempfile.TemporaryDirectory() as base:
            directory = model_directory("funasr/example", "funasr", base)
            directory.mkdir(parents=True)
            (directory / "model.pt").write_bytes(b"weights")
            for metadata in (
                None,
                "{",
                json.dumps({"model": "funasr/example", "revision": "old", "files": {"model.pt": 7}}),
                json.dumps({"model": "funasr/example", "revision": "commit", "files": {}}),
                json.dumps({"model": "other/model", "revision": "commit", "files": {"model.pt": 7}}),
                json.dumps({"model": "funasr/example", "revision": "commit", "files": {"model.pt": 99}}),
            ):
                with self.subTest(metadata=metadata):
                    if metadata is not None:
                        (directory / COMPLETION_FILE).write_text(metadata)
                    with self.assertRaisesRegex(RuntimeError, "provisioning job"):
                        get_local_model("funasr/example", "commit", models_base_path=base, required_files=["model.pt"])

    def test_deleted_or_empty_required_file_fails(self):
        with tempfile.TemporaryDirectory() as base:
            directory = model_directory("funasr/example", "funasr", base)
            directory.mkdir(parents=True)
            (directory / "model.pt").write_bytes(b"weights")
            record_snapshot("funasr/example", None, directory)
            (directory / "model.pt").unlink()
            with self.assertRaisesRegex(RuntimeError, "provisioning job"):
                get_local_model("funasr/example", models_base_path=base)
            (directory / "model.pt").touch()
            record_snapshot("funasr/example", None, directory)
            with self.assertRaisesRegex(RuntimeError, "provisioning job"):
                get_local_model("funasr/example", models_base_path=base, required_files=["model.pt"])

    def test_inventory_cannot_reference_files_outside_snapshot(self):
        with tempfile.TemporaryDirectory() as base:
            directory = model_directory("funasr/example", "funasr", base)
            directory.mkdir(parents=True)
            (directory / COMPLETION_FILE).write_text(json.dumps({
                "model": "funasr/example", "revision": None, "files": {"../../outside": 1},
            }))
            with self.assertRaisesRegex(RuntimeError, "provisioning job"):
                get_local_model("funasr/example", models_base_path=base)

    def test_invalid_identifiers_and_destinations_are_rejected(self):
        for model, destination in (("../escape", "funasr"), ("funasr/model", "../escape")):
            with self.subTest(model=model, destination=destination), self.assertRaises(ValueError):
                model_directory(model, destination, "models")


if __name__ == "__main__":
    unittest.main()
