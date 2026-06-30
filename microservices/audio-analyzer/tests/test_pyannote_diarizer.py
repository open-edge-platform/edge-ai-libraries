import os
import tempfile
import unittest

import numpy as np
import soundfile as sf

from components.asr.diarization.pyannote_diarizer import PyannoteDiarizer


class PyannoteDiarizerTests(unittest.TestCase):
    def test_diarize_reads_waveform_without_torchaudio_decoder(self):
        diarizer = PyannoteDiarizer.__new__(PyannoteDiarizer)

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
            def __call__(self, audio_input):
                captured.update(audio_input)
                return FakeOutput()

        diarizer.pipeline = FakePipeline()

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, "sample.wav")
            samples = np.linspace(-0.2, 0.2, 1600, dtype=np.float32)
            stereo = np.column_stack((samples, samples))
            sf.write(audio_path, stereo, 16000)

            result = diarizer.diarize(audio_path)

        self.assertEqual(result, [{"start": 0.0, "end": 0.5, "speaker": "SPEAKER_00"}])
        self.assertEqual(captured["sample_rate"], 16000)
        self.assertEqual(tuple(captured["waveform"].shape), (2, 1600))


if __name__ == "__main__":
    unittest.main()