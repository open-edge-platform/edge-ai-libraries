from pyannote.audio import Pipeline
import torch
from torch.serialization import safe_globals
import torch.torch_version
from pyannote.audio.core.task import Specifications, Problem, Resolution, Task


class PyannoteDiarizer:
    def __init__(self, device="cpu", hf_token=None):

        # Allow all needed globals for torch ≥2.6 checkpoint loading
        with safe_globals([
            torch.torch_version.TorchVersion,
            Specifications,
            Problem,
            Resolution,
            Task
        ]):
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token
            )

        self.device = torch.device(device)
        self.pipeline.to(self.device)

    def diarize(self, audio_path):
        diarization = self.pipeline(audio_path)
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": speaker
            })
        return segments
