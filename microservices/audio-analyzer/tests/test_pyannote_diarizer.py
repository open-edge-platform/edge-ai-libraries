import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf

from components.asr.diarization.pyannote_diarizer import PyannoteDiarizer
from components.asr.diarization import pyannote_diarizer as diarizer_module


class PyannoteDiarizerMapLocationRegressionTests(unittest.TestCase):
    """Regression coverage for ITEP-95359.

    The original failure: ``Pipeline.from_pretrained`` raised
    ``RuntimeError: don't know how to restore data location of
    torch.storage.UntypedStorage (tagged with gpu)`` when loading a
    checkpoint saved on a GPU machine without map_location=cpu.

    The fix: ``_load_pipeline_with_map_location_fallback`` retries with
    ``map_location='cpu'`` on that specific error, and the pipeline is
    moved to the target device afterward.
    """

    def test_non_gpu_tagged_error_is_not_retried_and_propagates(self):
        """Errors unrelated to GPU-tagged storage must not be swallowed."""

        def _fail_always(source, token=None):
            raise RuntimeError("some other load failure unrelated to storage tags")

        with patch.object(diarizer_module.Pipeline, "from_pretrained", side_effect=_fail_always):
            with self.assertRaises(RuntimeError, msg="some other load failure"):
                diarizer_module._load_pipeline_with_map_location_fallback(
                    "dummy/model", "hf_token"
                )

    def test_gpu_tagged_error_retries_exactly_once(self):
        """The GPU-tagged storage error triggers exactly one retry (not infinite)."""
        calls = []

        def _always_raise_gpu_tag(source, token=None):
            calls.append(source)
            raise RuntimeError(
                "don't know how to restore data location of "
                "torch.storage.UntypedStorage (tagged with gpu)"
            )

        with patch.object(diarizer_module.Pipeline, "from_pretrained", side_effect=_always_raise_gpu_tag):
            with self.assertRaises(RuntimeError):
                diarizer_module._load_pipeline_with_map_location_fallback(
                    "dummy/model", "hf_token"
                )
        # Called twice: original attempt + one retry with map_location=cpu.
        self.assertEqual(2, len(calls))

    def test_gpu_tagged_error_first_attempt_succeeds_on_retry(self):
        """After map_location=cpu retry the returned pipeline is the patched one."""
        calls = []

        def _fail_then_succeed(source, token=None):
            calls.append(source)
            if len(calls) == 1:
                raise RuntimeError(
                    "don't know how to restore data location of "
                    "torch.storage.UntypedStorage (tagged with gpu)"
                )
            return "pipeline-ok"

        with patch.object(diarizer_module.Pipeline, "from_pretrained", side_effect=_fail_then_succeed):
            pipeline = diarizer_module._load_pipeline_with_map_location_fallback(
                "dummy/model", "hf_token"
            )
        self.assertEqual("pipeline-ok", pipeline)
        self.assertEqual(2, len(calls))
class PyannoteDiarizerTests(unittest.TestCase):
    def test_gpu_tagged_storage_error_retries_pipeline_load(self):
        calls = []

        def _fake_from_pretrained(source, token=None):
            calls.append((source, token))
            if len(calls) == 1:
                raise RuntimeError(
                    "don't know how to restore data location of "
                    "torch.storage.UntypedStorage (tagged with gpu)"
                )
            return "pipeline-ok"

        with patch.object(diarizer_module.Pipeline, "from_pretrained", side_effect=_fake_from_pretrained):
            pipeline = diarizer_module._load_pipeline_with_map_location_fallback(
                "dummy/model",
                "hf_token",
            )

        self.assertEqual("pipeline-ok", pipeline)
        self.assertEqual(2, len(calls))
        self.assertEqual(("dummy/model", "hf_token"), calls[0])
        self.assertEqual(("dummy/model", "hf_token"), calls[1])

    def test_diarize_reads_waveform_without_torchaudio_decoder(self):
        diarizer = PyannoteDiarizer.__new__(PyannoteDiarizer)
        diarizer.min_speakers = 1
        diarizer.max_speakers = 2
        diarizer.voice_enrollment_enabled = False

        captured = {}

        class FakeDiarization:
            def itertracks(self, yield_label=False):
                self_yield_label = yield_label
                del self_yield_label
                turn = type("Turn", (), {"start": 0.0, "end": 0.5})()
                yield turn, None, "SPEAKER_00"

        class FakeOutput:
            exclusive_speaker_diarization = FakeDiarization()

        class FakePipeline:
            def __call__(self, audio_input, **kwargs):
                captured.update(audio_input)
                captured["kwargs"] = kwargs
                return FakeOutput()

        diarizer.pipeline = FakePipeline()

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, "sample.wav")
            samples = np.linspace(-0.2, 0.2, 1600, dtype=np.float32)
            stereo = np.column_stack((samples, samples))
            sf.write(audio_path, stereo, 16000)

            turns, label_embeddings = diarizer.diarize(audio_path)

        self.assertEqual(turns, [{"start": 0.0, "end": 0.5, "speaker": "SPEAKER_00"}])
        self.assertEqual(label_embeddings, {})
        self.assertEqual(captured["sample_rate"], 16000)
        self.assertEqual(tuple(captured["waveform"].shape), (2, 1600))
        self.assertEqual(captured["kwargs"], {"min_speakers": 1, "max_speakers": 2})

    def test_diarize_extracts_label_embeddings_from_output(self):
        diarizer = PyannoteDiarizer.__new__(PyannoteDiarizer)
        diarizer.min_speakers = 1
        diarizer.max_speakers = 2
        diarizer.voice_enrollment_enabled = False

        class FakeDiarization:
            def itertracks(self, yield_label=False):
                del yield_label
                turn = type("Turn", (), {"start": 0.0, "end": 0.5})()
                yield turn, None, "SPEAKER_00"

        class FakeSpeakerDiarization:
            def labels(self):
                return ["SPEAKER_00", "SPEAKER_01"]

        class FakeOutput:
            exclusive_speaker_diarization = FakeDiarization()
            speaker_diarization = FakeSpeakerDiarization()
            speaker_embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

        class FakePipeline:
            def __call__(self, audio_input, **kwargs):
                del audio_input, kwargs
                return FakeOutput()

        diarizer.pipeline = FakePipeline()

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, "sample.wav")
            samples = np.linspace(-0.2, 0.2, 1600, dtype=np.float32)
            stereo = np.column_stack((samples, samples))
            sf.write(audio_path, stereo, 16000)

            _, label_embeddings = diarizer.diarize(audio_path)

        self.assertEqual(set(label_embeddings.keys()), {"SPEAKER_00", "SPEAKER_01"})
        np.testing.assert_array_equal(label_embeddings["SPEAKER_00"], [1.0, 0.0])
        np.testing.assert_array_equal(label_embeddings["SPEAKER_01"], [0.0, 1.0])


if __name__ == "__main__":
    unittest.main()