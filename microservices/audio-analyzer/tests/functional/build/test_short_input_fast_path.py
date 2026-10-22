# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for the short-input fast paths added for ASR latency.

Covers:
- ``utils.wav_header`` RIFF parsing, including truncated files and the
  ``0xFFFFFFFF`` placeholder size ffmpeg writes while still recording.
- ``PcmStreamBuffer.peek`` / ``peek_tail`` non-destructive reads.
- The ffmpeg pass-through in ``process_audio_segment``, which must be disabled
  whenever an audio filter (denoise OR loudness normalization) is configured.
- ``utils.asr_model_capabilities.is_english_only_model``.
- ``utils.asr_pool_config`` per-pool resolution, where every ``models.asr.preview``
  key is optional and must fall back to the main ASR config.
"""

import struct
import sys
import unittest
import wave
from unittest.mock import MagicMock, patch

import pytest

# Stub heavy ML libraries before any app import (mirrors the sibling tests).
for _mod in [
    "torch", "torch.serialization", "torch.torch_version",
    "pyannote", "pyannote.audio", "pyannote.audio.core", "pyannote.audio.core.task",
    "openvino", "openvino_genai",
    "librosa", "soundfile", "sounddevice",
    "whisper", "whispercpp",
]:
    sys.modules.setdefault(_mod, MagicMock())

from utils.asr_model_capabilities import is_english_only_model  # noqa: E402
from utils.pcm_audio import PcmStreamBuffer  # noqa: E402
from utils.wav_header import read_pcm_wav_info  # noqa: E402

pytestmark = pytest.mark.tier1

SAMPLE_RATE = 16000


def _write_wav(path, seconds=1.0, sample_rate=SAMPLE_RATE, channels=1, sample_width=2):
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00" * frames * channels * sample_width)
    return path


# ---------------------------------------------------------------------------
# wav_header
# ---------------------------------------------------------------------------

class TestReadPcmWavInfo:
    def test_reads_duration_and_format(self, tmp_path):
        info = read_pcm_wav_info(str(_write_wav(tmp_path / "a.wav", seconds=1.5)))

        assert info is not None
        assert info.duration_seconds == pytest.approx(1.5)
        assert info.sample_rate == SAMPLE_RATE
        assert info.channels == 1
        assert info.sample_width == 2
        assert info.matches_target_format() is True

    def test_non_target_format_is_reported(self, tmp_path):
        info = read_pcm_wav_info(
            str(_write_wav(tmp_path / "b.wav", sample_rate=44100, channels=2))
        )

        assert info is not None
        assert info.matches_target_format() is False

    def test_non_wav_extension_returns_none(self, tmp_path):
        path = tmp_path / "c.mp3"
        path.write_bytes(b"not a wav")

        assert read_pcm_wav_info(str(path)) is None

    def test_truncated_file_clamps_to_bytes_on_disk(self, tmp_path):
        path = _write_wav(tmp_path / "d.wav", seconds=4.0)
        data = path.read_bytes()
        # Keep the header's declared 4s but drop half the samples.
        path.write_bytes(data[: 44 + (len(data) - 44) // 2])

        info = read_pcm_wav_info(str(path))

        assert info is not None
        assert info.duration_seconds == pytest.approx(2.0, abs=0.01)

    def test_streaming_placeholder_size_is_clamped(self, tmp_path):
        """ffmpeg writes 0xFFFFFFFF sizes while a recording is in progress."""
        path = _write_wav(tmp_path / "e.wav", seconds=1.0)
        data = bytearray(path.read_bytes())
        data[4:8] = struct.pack("<I", 0xFFFFFFFF)    # RIFF size
        data[40:44] = struct.pack("<I", 0xFFFFFFFF)  # data chunk size
        path.write_bytes(bytes(data))

        info = read_pcm_wav_info(str(path))

        assert info is not None
        assert info.duration_seconds == pytest.approx(1.0, abs=0.01)

    def test_header_only_file_returns_none(self, tmp_path):
        path = _write_wav(tmp_path / "f.wav", seconds=1.0)
        path.write_bytes(path.read_bytes()[:44])

        assert read_pcm_wav_info(str(path)) is None

    def test_garbage_file_returns_none(self, tmp_path):
        path = tmp_path / "g.wav"
        path.write_bytes(b"RIFFnot-really-a-wav-at-all")

        assert read_pcm_wav_info(str(path)) is None


# ---------------------------------------------------------------------------
# PcmStreamBuffer peek / peek_tail
# ---------------------------------------------------------------------------

class TestPcmStreamBufferPeek:
    def _buffer(self, seconds):
        buffer = PcmStreamBuffer(sample_rate=SAMPLE_RATE)
        buffer.append(b"\x01\x00" * int(seconds * SAMPLE_RATE))
        return buffer

    def test_peek_does_not_consume(self):
        buffer = self._buffer(1.0)

        first = buffer.peek()
        second = buffer.peek()

        assert first == second
        assert len(buffer.take()) == len(first)

    def test_peek_tail_limits_window(self):
        buffer = self._buffer(5.0)

        tail = buffer.peek_tail(2.0)

        assert len(tail) == 2 * SAMPLE_RATE * 2
        assert len(buffer.peek()) == 5 * SAMPLE_RATE * 2

    def test_peek_tail_returns_everything_when_shorter_than_window(self):
        buffer = self._buffer(0.5)

        assert buffer.peek_tail(2.0) == buffer.peek()

    def test_peek_tail_is_sample_aligned(self):
        buffer = self._buffer(5.0)

        tail = buffer.peek_tail(1.00003)

        assert len(tail) % 2 == 0


# ---------------------------------------------------------------------------
# ffmpeg pass-through
# ---------------------------------------------------------------------------

class TestProcessAudioSegmentPassthrough:
    def test_passthrough_skips_ffmpeg_for_target_format_wav(self, tmp_path):
        from components.ffmpeg import audio_preprocessing as ap

        path = str(_write_wav(tmp_path / "in.wav", seconds=1.0))
        with patch.object(ap, "DENOISE", False), patch.object(ap, "NORMALIZE", False), \
                patch.object(ap, "subprocess") as subprocess_mock:
            chunk = ap.process_audio_segment(path, 0.0, 1.0, 0, full_file=True)

        subprocess_mock.run.assert_not_called()
        assert chunk["passthrough"] is True
        assert chunk["chunk_path"] == path

    def test_normalization_disables_passthrough(self, tmp_path):
        """A configured -af filter must apply to short inputs too."""
        from components.ffmpeg import audio_preprocessing as ap

        path = str(_write_wav(tmp_path / "in.wav", seconds=1.0))
        with patch.object(ap, "DENOISE", False), patch.object(ap, "NORMALIZE", True), \
                patch.object(ap, "NORMALIZE_FILTER", "dynaudnorm"):
            assert ap._build_af_filter() == ["-af", "dynaudnorm"]
            with patch.object(ap, "subprocess") as subprocess_mock, \
                    patch.object(ap.os.path, "isfile", return_value=True):
                subprocess_mock.run.return_value = MagicMock(returncode=0, stderr="")
                chunk = ap.process_audio_segment(path, 0.0, 1.0, 0, full_file=True)

        subprocess_mock.run.assert_called_once()
        assert "passthrough" not in chunk

    def test_denoise_disables_passthrough(self, tmp_path):
        from components.ffmpeg import audio_preprocessing as ap

        with patch.object(ap, "DENOISE", True), patch.object(ap, "DENOISE_MODEL", ""), \
                patch.object(ap, "NORMALIZE", False):
            assert ap._build_af_filter() == ["-af", "afftdn"]

    def test_filters_chain_in_order(self):
        from components.ffmpeg import audio_preprocessing as ap

        with patch.object(ap, "DENOISE", True), patch.object(ap, "DENOISE_MODEL", ""), \
                patch.object(ap, "NORMALIZE", True), patch.object(ap, "NORMALIZE_FILTER", "dynaudnorm"):
            assert ap._build_af_filter() == ["-af", "afftdn,dynaudnorm"]


# ---------------------------------------------------------------------------
# English-only model detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_name,expected", [
    ("distil-whisper/distil-small.en", True),
    ("whisper-base.en", True),
    ("WHISPER-BASE.EN", True),
    ("whisper-small", False),
    ("paraformer-zh", False),
    ("", False),
    (None, False),
])
def test_is_english_only_model(model_name, expected):
    assert is_english_only_model(model_name) is expected


_MISSING = object()


class AsrPoolConfigResolutionTests(unittest.TestCase):
    """`models.asr.preview` keys are all optional and must fall back safely."""

    def setUp(self):
        from utils.config_loader import config as _config

        self.asr = _config.models.asr
        self._saved = {
            k: getattr(self.asr, k, _MISSING)
            for k in ("preview", "name", "device", "provider", "weight_format")
        }

    def tearDown(self):
        for key, value in self._saved.items():
            if value is _MISSING:
                if hasattr(self.asr, key):
                    delattr(self.asr, key)
            else:
                setattr(self.asr, key, value)

    def _set_main(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self.asr, key, value)

    def test_preview_with_only_device_inherits_name_and_provider(self):
        """A preview block that sets just `device:` must not raise."""
        from types import SimpleNamespace
        from utils import asr_pool_config as apc

        self._set_main(name="whisper-small", provider="openvino",
                       device="CPU", weight_format="int8")
        self.asr.preview = SimpleNamespace(device="GPU")

        cfg = apc.resolve_pool_config(apc.POOL_PREVIEW)
        self.assertEqual(cfg.name, "whisper-small")
        self.assertEqual(cfg.provider, "openvino")
        self.assertEqual(cfg.weight_format, "int8")
        self.assertEqual(cfg.device, "GPU")

    def test_preview_with_empty_block_falls_back_entirely(self):
        from types import SimpleNamespace
        from utils import asr_pool_config as apc

        self._set_main(name="whisper-small", provider="openvino",
                       device="CPU", weight_format="int8")
        self.asr.preview = SimpleNamespace()

        cfg = apc.resolve_pool_config(apc.POOL_PREVIEW)
        final = apc.resolve_pool_config(apc.POOL_FINAL)
        self.assertEqual(cfg.name, final.name)
        self.assertEqual(cfg.device, final.device)
        self.assertFalse(apc.preview_differs_from_final())

    def test_device_only_preview_needs_no_extra_model_export(self):
        """Same model on another device must not trigger a second export."""
        from types import SimpleNamespace
        from utils import asr_pool_config as apc

        self._set_main(name="whisper-small", provider="openvino",
                       device="CPU", weight_format="int8")
        self.asr.preview = SimpleNamespace(device="GPU")
        self.assertFalse(apc.preview_differs_from_final())

    def test_different_preview_model_requires_export(self):
        from types import SimpleNamespace
        from utils import asr_pool_config as apc

        self._set_main(name="whisper-small", provider="openvino",
                       device="CPU", weight_format="int8")
        self.asr.preview = SimpleNamespace(name="whisper-tiny.en")
        self.assertTrue(apc.preview_differs_from_final())
        self.assertEqual(apc.resolve_pool_config(apc.POOL_PREVIEW).name, "whisper-tiny.en")

    def test_no_preview_block_is_not_a_difference(self):
        from utils import asr_pool_config as apc

        if hasattr(self.asr, "preview"):
            delattr(self.asr, "preview")
        self.assertFalse(apc.preview_differs_from_final())
        self.assertEqual(
            apc.resolve_pool_config(apc.POOL_PREVIEW).name,
            apc.resolve_pool_config(apc.POOL_FINAL).name,
        )

    def test_unknown_pool_name_is_rejected(self):
        from utils import asr_pool_config as apc

        with self.assertRaises(ValueError):
            apc.resolve_pool_config("bogus")

    def test_device_override_applies_to_final_pool_only(self):
        from types import SimpleNamespace
        from utils import asr_pool_config as apc

        self._set_main(name="whisper-small", provider="openvino", device="CPU")
        self.asr.preview = SimpleNamespace(device="NPU")
        self.assertEqual(
            apc.resolve_pool_config(apc.POOL_FINAL, device_override="GPU").device, "GPU"
        )
        self.assertEqual(
            apc.resolve_pool_config(apc.POOL_PREVIEW, device_override="GPU").device, "NPU"
        )


class PreviewProviderValidationTests(AsrPoolConfigResolutionTests):
    """`models.asr.preview.provider` must match the main provider."""

    def test_mismatched_provider_is_rejected_at_startup(self):
        from types import SimpleNamespace
        from utils.config_loader import config as _config
        from utils import openvino_runtime_validation as orv

        self._set_main(name="whisper-small", provider="openvino", device="CPU")
        self.asr.preview = SimpleNamespace(provider="whispercpp", name="whisper-tiny")

        with self.assertRaises(ValueError) as ctx:
            orv.validate_asr_preview_configuration(_config)
        self.assertIn("preview.provider", str(ctx.exception))

    def test_matching_provider_passes_validation(self):
        from types import SimpleNamespace
        from utils.config_loader import config as _config
        from utils import openvino_runtime_validation as orv

        self._set_main(name="whisper-small", provider="openvino", device="CPU")
        self.asr.preview = SimpleNamespace(name="whisper-tiny.en")

        with patch.object(orv, "resolve_asr_device", return_value="CPU") as resolve:
            orv.validate_asr_preview_configuration(_config)
        resolve.assert_called_once()

    def test_no_preview_block_skips_validation_entirely(self):
        from utils.config_loader import config as _config
        from utils import openvino_runtime_validation as orv

        if hasattr(self.asr, "preview"):
            delattr(self.asr, "preview")
        with patch.object(orv, "resolve_asr_device") as resolve:
            orv.validate_asr_preview_configuration(_config)
        resolve.assert_not_called()

    def test_preview_device_is_validated_at_startup(self):
        """An unavailable preview device must fail at startup, not first use."""
        from types import SimpleNamespace
        from utils.config_loader import config as _config
        from utils import openvino_runtime_validation as orv

        self._set_main(name="whisper-small", provider="openvino", device="CPU")
        self.asr.preview = SimpleNamespace(device="NPU")

        with patch.object(orv, "resolve_asr_device", side_effect=ValueError("NPU not available")):
            with self.assertRaises(ValueError):
                orv.validate_asr_preview_configuration(_config)


class BackendModelNameCaseTests(unittest.TestCase):
    """The backend must receive the configured model name, not a lower-cased one.

    Backends derive their on-disk directory from this string, and ensure_model
    exported it under the configured spelling.
    """

    def tearDown(self):
        from components.asr_component import ASRComponent

        ASRComponent._models = {}

    def test_configured_case_is_preserved_when_constructing_backend(self):
        from components.asr_component import ASRComponent

        built = []

        class FakeBackend:
            def __init__(self, model_name, device, revision):
                built.append(model_name)

        with patch.object(
            ASRComponent, "_resolve_backend",
            return_value=(FakeBackend, ("openvino", "distil-whisper/distil-small.en", "CPU", False), "CPU"),
        ):
            ASRComponent(
                "sess", provider="openvino",
                model_name="distil-whisper/Distil-Small.EN", device="CPU",
            )

        self.assertEqual(built, ["distil-whisper/Distil-Small.EN"])

    def test_cache_key_still_normalizes_case(self):
        """Equivalent configs differing only in case must share one instance."""
        from components.asr_component import ASRComponent

        built = []

        class FakeBackend:
            def __init__(self, model_name, device, revision):
                built.append(model_name)

        key = ("openvino", "whisper-small", "CPU", False)
        with patch.object(ASRComponent, "_resolve_backend", return_value=(FakeBackend, key, "CPU")):
            a = ASRComponent("s1", provider="openvino", model_name="Whisper-Small", device="CPU")
            b = ASRComponent("s2", provider="openvino", model_name="whisper-small", device="CPU")

        self.assertEqual(len(built), 1)
        self.assertIs(a.asr, b.asr)

    def test_pools_do_not_share_a_cache_entry(self):
        from components.asr_component import ASRComponent

        built = []

        class FakeBackend:
            def __init__(self, model_name, device, revision):
                built.append(model_name)

        key = ("openvino", "whisper-small", "CPU", False)
        with patch.object(ASRComponent, "_resolve_backend", return_value=(FakeBackend, key, "CPU")):
            final = ASRComponent("s1", provider="openvino", model_name="whisper-small",
                                 device="CPU", pool="final")
            preview = ASRComponent("s2", provider="openvino", model_name="whisper-small",
                                   device="CPU", pool="preview")

        self.assertEqual(len(built), 2)
        self.assertIsNot(final.asr, preview.asr)
