import os
import tempfile
import unittest

import numpy as np
import soundfile as sf

from components.asr.diarization.pyannote_diarizer import PyannoteDiarizer


class PyannoteDiarizerTests(unittest.TestCase):
    def test_diarize_reads_waveform_without_torchaudio_decoder(self):
        diarizer = PyannoteDiarizer.__new__(PyannoteDiarizer)
        diarizer.min_speakers = 1
        diarizer.max_speakers = 2

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