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
        # Kiosk scenario: at most one customer + one staff member per chunk.
        # Constraining speaker count reduces phantom speakers on short/noisy audio.
        self.min_speakers = getattr(diar_cfg, "min_speakers", 1)
        self.max_speakers = getattr(diar_cfg, "max_speakers", 2)

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

    def diarize(self, audio_path: str) -> tuple[list[dict], dict[str, np.ndarray]]:
        """Return speaker turn segments and per-speaker embeddings for the given audio file.

        Returns:
            Tuple of:
              - List of dicts with keys ``start``, ``end``, ``speaker``.
              - Dict mapping each local speaker label (e.g. ``"SPEAKER_00"``) to
                its mean embedding for this chunk, as computed internally by the
                pyannote pipeline during clustering (``DiarizeOutput.speaker_embeddings``).
                Empty if the pipeline could not produce embeddings (e.g. silence).
        """
        waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
        waveform = np.ascontiguousarray(waveform.T)
        waveform = torch.from_numpy(waveform)
        audio_input = {"waveform": waveform, "sample_rate": sample_rate}
        output = self.pipeline(
            audio_input,
            min_speakers=self.min_speakers,
            max_speakers=self.max_speakers,
        )
        diarization = output.exclusive_speaker_diarization
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": speaker,
            })

        label_embeddings: dict[str, np.ndarray] = {}
        speaker_embeddings = getattr(output, "speaker_embeddings", None)
        if speaker_embeddings is not None:
            # speaker_embeddings rows are ordered to match
            # output.speaker_diarization.labels() (see pyannote DiarizeOutput).
            labels = output.speaker_diarization.labels()
            for label, embedding in zip(labels, speaker_embeddings):
                if embedding is not None and np.any(embedding):
                    label_embeddings[label] = embedding

        return segments, label_embeddings
