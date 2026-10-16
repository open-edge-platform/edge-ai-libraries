# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import utils.ensure_model as ensure_model


def _cfg(*, diarization_enabled: bool, hf_token: str | None):
    return SimpleNamespace(
        models=SimpleNamespace(
            asr=SimpleNamespace(
                provider="openvino",
                name="whisper-base",
                device="CPU",
                diarization=diarization_enabled,
                hf_token=hf_token,
                models_base_path="models",
                weight_format=None,
            ),
            diarization=SimpleNamespace(
                provider="huggingface",
                name="pyannote/speaker-diarization-community-1",
                models_base_path="models",
            ),
        ),
        sentiment=SimpleNamespace(enabled=False),
    )


class EnsureModelDiarizationStartupPolicyTests(unittest.TestCase):
    def test_ensure_model_fails_when_diarization_enabled_without_hf_token(self):
        cfg = _cfg(diarization_enabled=True, hf_token=None)
        with patch.object(ensure_model, "config", cfg), patch.object(
            ensure_model, "_download_openvino_model", return_value=(True, "/tmp/asr")
        ):
            with self.assertRaisesRegex(RuntimeError, "HF_TOKEN is not configured"):
                ensure_model.ensure_model()

    def test_ensure_model_propagates_downloader_access_error(self):
        cfg = _cfg(diarization_enabled=True, hf_token="hf_bad")
        with patch.object(ensure_model, "config", cfg), patch.object(
            ensure_model, "_download_openvino_model", return_value=(True, "/tmp/asr")
        ), patch.object(ensure_model, "_download_hf_model", side_effect=RuntimeError("403 Forbidden")):
            with self.assertRaisesRegex(RuntimeError, "403 Forbidden"):
                ensure_model.ensure_model()

    def test_ensure_model_allows_missing_hf_token_when_diarization_disabled(self):
        cfg = _cfg(diarization_enabled=False, hf_token=None)
        with patch.object(ensure_model, "config", cfg), patch.object(
            ensure_model, "_download_openvino_model", return_value=(True, "/tmp/asr")
        ):
            ensure_model.ensure_model()


if __name__ == "__main__":
    unittest.main()
