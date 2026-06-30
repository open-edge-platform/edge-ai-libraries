import os
import numpy as np
import torch
import soundfile as sf
from torch.serialization import safe_globals
import torch.torch_version
from pyannote.audio import Pipeline
from pyannote.audio.core.task import Specifications, Problem, Resolution, Task
from utils.ensure_model import get_diarization_model_path
from utils.config_loader import config


class PyannoteDiarizer:
    def __init__(self, device: str = "cpu", hf_token: str | None = None):
        diar_cfg = config.models.diarization
        pipeline_source = diar_cfg.name

        # Prefer locally cached snapshot (offline-capable); fall back to HF Hub
        local_model_path = get_diarization_model_path()
        local_config_path = os.path.join(local_model_path, "config.yaml")
        if os.path.exists(local_config_path):
            pipeline_source = local_config_path

        # Allow all pyannote checkpoint globals required by torch ≥ 2.6
        with safe_globals([
            torch.torch_version.TorchVersion,
            Specifications,
            Problem,
            Resolution,
            Task,
        ]):
            self.pipeline = Pipeline.from_pretrained(
                pipeline_source,
                token=hf_token,
            )

        self.device = torch.device(device)
        self.pipeline.to(self.device)

    def diarize(self, audio_path: str) -> list[dict]:
        """Return speaker turn segments for the given audio file.

        Returns:
            List of dicts with keys ``start``, ``end``, ``speaker``.
        """
        waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
        waveform = np.ascontiguousarray(waveform.T)
        waveform = torch.from_numpy(waveform)
        audio_input = {"waveform": waveform, "sample_rate": sample_rate}
        output = self.pipeline(audio_input)
        diarization = output.exclusive_speaker_diarization
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": speaker,
            })
        return segments
