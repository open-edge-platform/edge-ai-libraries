# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
import unittest
import base64
from pathlib import Path
from unittest.mock import patch

from utils import ensure_model
from utils.model_download_client import get_model_from_service


class SharedModelTests(unittest.TestCase):
    def test_openvino_exports_locally_downloaded_hf_snapshot(self):
        with tempfile.TemporaryDirectory() as base, \
             patch.object(ensure_model, "_ir_exists", side_effect=[False, True]), \
             patch.object(ensure_model, "get_model_from_service", return_value="/shared/whisper") as fetch, \
             patch.object(ensure_model, "run_cli", return_value=0) as run:
            success, _ = ensure_model._download_openvino_model("openai/whisper-base", base, None)
        self.assertTrue(success)
        fetch.assert_called_once_with(
            "openai/whisper-base", hub="huggingface", download_path="whisper-source",
            required_files=["config.json"],
        )
        self.assertEqual(run.call_args.kwargs["cmd"][run.call_args.kwargs["cmd"].index("--model") + 1], "/shared/whisper")

    def test_whispercpp_uses_single_requested_file(self):
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as source:
            (Path(source) / "ggml-base.bin").write_bytes(b"weights")
            with patch.object(ensure_model, "get_model_from_service", return_value=source) as fetch:
                self.assertTrue(ensure_model._download_whispercpp_model("whisper-base", base))
            fetch.assert_called_once_with(
                "ggerganov/whisper.cpp", hub="huggingface", download_path="whisper-source",
                files=["ggml-base.bin"], required_files=["ggml-base.bin"],
            )
            self.assertEqual((Path(base) / "ggml-base.bin").read_bytes(), b"weights")

    def test_openai_whisper_requests_official_checkpoint(self):
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as source:
            (Path(source) / "base.pt").write_bytes(b"weights")
            with patch.object(ensure_model.config.models.asr, "provider", "openai"), \
                 patch.object(ensure_model.config.models.asr, "name", "whisper-base"), \
                 patch.object(ensure_model, "get_asr_model_path", return_value=base), \
                 patch.object(ensure_model, "get_model_from_service", return_value=source) as fetch:
                ensure_model.ensure_model()
            fetch.assert_called_once_with(
                "base", hub="openai-whisper", download_path="whisper-source",
                required_files=["base.pt"],
            )
            self.assertEqual((Path(base) / "base.pt").read_bytes(), b"weights")

    def test_pyannote_download_is_delegated(self):
        with patch.object(ensure_model, "get_model_from_service", return_value="/shared/diar") as fetch:
            self.assertEqual(
                ensure_model._download_hf_model("pyannote/example", "/unused", required_files=["config.yaml"]),
                (True, "/shared/diar"),
            )
        fetch.assert_called_once_with(
            "pyannote/example", hub="huggingface", download_path="diarization",
            required_files=["config.yaml"], hf_token=None,
            models_base_path=ensure_model.config.models.diarization.models_base_path,
        )

    def test_hf_request_requires_shared_files(self):
        job_id = "e8f1892a-8c08-401f-a37a-d48957f206c1"
        with tempfile.TemporaryDirectory() as base, \
             patch.dict(os.environ, {"AUDIO_ANALYZER_MODEL_DOWNLOAD_URL": "http://model-downloader:8000"}), \
             patch("utils.model_download_client.config.models.asr.models_base_path", base), \
             patch("utils.model_download_client._request_json", side_effect=[
                 {"job_ids": [job_id]},
                 {"status": "completed", "result": {"source": "huggingface", "model_name": "pyannote/example"}},
             ]):
            with self.assertRaisesRegex(RuntimeError, "shared models volume"):
                get_model_from_service(
                    "pyannote/example", hub="huggingface", download_path="diarization",
                    required_files=["config.yaml"],
                )

    def test_gated_diarization_token_is_sent_as_request_override(self):
        job_id = "e8f1892a-8c08-401f-a37a-d48957f206c1"
        with tempfile.TemporaryDirectory() as base, \
             patch.dict(os.environ, {"AUDIO_ANALYZER_MODEL_DOWNLOAD_URL": "http://model-downloader:8000"}), \
             patch("utils.model_download_client.config.models.asr.models_base_path", base), \
             patch("utils.model_download_client._request_json", side_effect=[
                 {"job_ids": [job_id]},
                 {"status": "failed", "error": "access denied"},
             ]) as request:
            with self.assertRaisesRegex(RuntimeError, "access denied"):
                get_model_from_service(
                    "pyannote/example", hub="huggingface", download_path="diarization",
                    hf_token="hf_example",
                )
        self.assertEqual(
            request.call_args_list[0].args[1]["models"][0]["override_credentials"],
            {"HF_TOKEN": base64.b64encode(b"hf_example").decode("ascii")},
        )


if __name__ == "__main__":
    unittest.main()
