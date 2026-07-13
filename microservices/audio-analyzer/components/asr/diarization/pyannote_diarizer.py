import logging
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

logger = logging.getLogger(__name__)


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

        # Allow all pyannote checkpoint globals required by torch >= 2.6
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

        # ── Clustering aggressiveness overrides ────────────────────────────
        # For single-mic kiosk scenarios the default pyannote thresholds
        # collapse acoustically similar co-located speakers into one label.
        # Config keys (all optional):
        #   diarization.clustering_threshold   → lower → more speakers
        #   diarization.segmentation_threshold → lower → more speech turns
        clustering_threshold = getattr(diar_cfg, "clustering_threshold", None)
        segmentation_threshold = getattr(diar_cfg, "segmentation_threshold", None)
        if clustering_threshold is not None or segmentation_threshold is not None:
            self._apply_hyperparameters(clustering_threshold, segmentation_threshold)

        # ── Session-level voice enrollment ──────────────────────────────────
        # Per-session "primary" speaker embedding: on the first sufficiently-long
        # turn we enroll it, then relabel every subsequent turn by cosine
        # similarity to that reference. Used as a fallback when pyannote's
        # clustering merges co-located voices (common on single-mic kiosks).
        self.voice_enrollment_enabled = bool(
            getattr(diar_cfg, "voice_enrollment_enabled", False)
        )
        self.voice_match_threshold = float(
            getattr(diar_cfg, "voice_match_threshold", 0.5)
        )
        self.min_enrollment_duration = float(
            getattr(diar_cfg, "min_enrollment_duration", 1.0)
        )
        # session_id → L2-normalized primary embedding
        self._primary_embeddings: dict[str, np.ndarray] = {}

    def reset_enrollment(self, session_id: str | None = None) -> None:
        """Drop enrolled primary speaker embedding(s).

        If ``session_id`` is provided, only that session's enrollment is
        cleared. Otherwise all enrollments are dropped.
        """
        if session_id is None:
            self._primary_embeddings.clear()
        else:
            self._primary_embeddings.pop(session_id, None)

    def _apply_hyperparameters(
        self,
        clustering_threshold: float | None,
        segmentation_threshold: float | None,
    ) -> None:
        """Override pipeline clustering/segmentation thresholds in-place.

        pyannote/speaker-diarization-3.1 exposes tunable hyperparameters via
        the pipeline attribute tree. We mutate them post-load rather than
        re-instantiating so cached weights are retained.
        """
        try:
            if clustering_threshold is not None and hasattr(self.pipeline, "clustering"):
                self.pipeline.clustering.threshold = float(clustering_threshold)
            if segmentation_threshold is not None and hasattr(self.pipeline, "segmentation"):
                # 3.1 uses segmentation.threshold; older pipelines used _segmentation
                self.pipeline.segmentation.threshold = float(segmentation_threshold)
        except (AttributeError, ValueError):
            # Silently ignore — hyperparameters vary between pipeline versions
            pass

    def label_whisper_segments(
        self,
        audio_path: str,
        whisper_segments: list[dict],
        session_id: str | None = None,
    ) -> list[dict]:
        """Assign SPEAKER_00/SPEAKER_01 labels per whisper segment via voice enrollment.

        Unlike :meth:`diarize`, this method bypasses pyannote's clustering
        step and extracts an embedding for each whisper segment's own time
        range, then compares to the session's enrolled primary embedding.
        This is more robust when pyannote merges two co-located voices into a
        single turn — whisper's temporal segmentation is typically sharper, so
        a secondary speaker's utterance still gets a distinct embedding and
        therefore a distinct SPEAKER_01 label.

        Args:
            audio_path: path to the chunk WAV.
            whisper_segments: list of dicts each with ``start`` and ``end``
                keys (chunk-local seconds). Extra keys (``text`` etc.) are
                preserved in the output.
            session_id: kiosk session id — scopes the enrolled primary
                embedding across chunks.

        Returns:
            A list of the same length as ``whisper_segments`` with each
            item augmented with a ``speaker`` field
            (``SPEAKER_00`` = primary, ``SPEAKER_01`` = secondary). If
            voice enrollment is disabled or the audio cannot be read, the
            input list is returned unchanged.
        """
        if not self.voice_enrollment_enabled or not whisper_segments:
            return whisper_segments
        try:
            waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
            waveform_tensor = torch.from_numpy(np.ascontiguousarray(waveform.T))
            adapted = [
                {
                    "start": float(s.get("start", 0.0)),
                    "end": float(s.get("end", 0.0)),
                    "speaker": s.get("speaker", ""),
                }
                for s in whisper_segments
            ]
            labeled = self._relabel_with_enrollment(
                adapted, waveform_tensor, sample_rate, session_id
            )
            # Merge the enrollment labels back into the caller's segment dicts
            # so metadata like ``text`` is preserved.
            out: list[dict] = []
            for src, lbl in zip(whisper_segments, labeled):
                merged = dict(src)
                merged["speaker"] = lbl.get("speaker", src.get("speaker", ""))
                out.append(merged)
            return out
        except Exception as exc:
            logger.warning(
                "[DIARIZATION] per-segment enrollment labeling failed (%s); "
                "falling back to caller-provided labels", exc,
            )
            return whisper_segments

    def diarize(
        self, audio_path: str, session_id: str | None = None
    ) -> tuple[list[dict], dict[str, np.ndarray]]:
        """Return speaker turn segments and per-speaker embeddings for the given audio file.

        Args:
            audio_path: path to the audio chunk to diarize.
            session_id: optional kiosk session identifier. When voice
                enrollment is enabled, the enrolled primary embedding is
                cached per ``session_id`` so subsequent chunks of the same
                kiosk session reuse the same reference voice.

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
        waveform_tensor = torch.from_numpy(waveform)
        audio_input = {"waveform": waveform_tensor, "sample_rate": sample_rate}

        # Pass speaker count hints when configured so the clustering step
        # is forced to surface at least min_speakers clusters.
        pipeline_kwargs: dict = {}
        if self.min_speakers is not None:
            pipeline_kwargs["min_speakers"] = int(self.min_speakers)
        if self.max_speakers is not None:
            pipeline_kwargs["max_speakers"] = int(self.max_speakers)

        output = self.pipeline(audio_input, **pipeline_kwargs)
        diarization = output.exclusive_speaker_diarization
        segments: list[dict] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": speaker,
            })

        if self.voice_enrollment_enabled and segments:
            try:
                segments = self._relabel_with_enrollment(
                    segments, waveform_tensor, sample_rate, session_id
                )
            except Exception as exc:
                # Never break the pipeline — fall back to pyannote labels
                logger.warning(
                    "[DIARIZATION] voice-enrollment relabel failed (%s); "
                    "falling back to pyannote labels", exc,
                )

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

    # ── Voice-enrollment helpers ────────────────────────────────────────────

    def _extract_embedding(
        self,
        waveform: torch.Tensor,
        sample_rate: int,
        start_s: float,
        end_s: float,
    ) -> np.ndarray | None:
        """Extract an L2-normalized WeSpeaker embedding for a turn slice."""
        start_idx = max(0, int(start_s * sample_rate))
        end_idx = min(waveform.shape[-1], int(end_s * sample_rate))
        if end_idx - start_idx < int(0.25 * sample_rate):  # < 250ms → skip
            return None

        clip = waveform[:, start_idx:end_idx].to(self.device)
        # WeSpeaker/pyannote embedding expects shape (batch, channel, time)
        if clip.dim() == 2:
            clip = clip.unsqueeze(0)

        embedding_model = getattr(self.pipeline, "_embedding", None)
        if embedding_model is None:
            return None

        with torch.no_grad():
            emb = embedding_model(clip)
        if isinstance(emb, torch.Tensor):
            emb = emb.detach().cpu().numpy()
        emb = np.asarray(emb, dtype=np.float32).squeeze()
        if emb.ndim == 0 or not np.isfinite(emb).all():
            return None

        norm = np.linalg.norm(emb)
        if norm < 1e-8:
            return None
        return (emb / norm).astype(np.float32)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))  # both already L2-normalized

    def _relabel_with_enrollment(
        self,
        segments: list[dict],
        waveform: torch.Tensor,
        sample_rate: int,
        session_id: str | None,
    ) -> list[dict]:
        """Relabel each segment as SPEAKER_00 (primary) or SPEAKER_01
        based on cosine similarity to the enrolled primary embedding
        for ``session_id``.

        On the first invocation of a session, uses the longest qualifying
        turn as the enrollment sample. If ``session_id`` is None, a shared
        ``"__default__"`` bucket is used (still persists across chunks).
        """
        session_key = session_id or "__default__"

        # Compute embeddings for every turn upfront (cache for reuse)
        turn_embeddings: list[np.ndarray | None] = [
            self._extract_embedding(waveform, sample_rate, s["start"], s["end"])
            for s in segments
        ]

        primary_embedding = self._primary_embeddings.get(session_key)
        if primary_embedding is None:
            # Enroll on the longest turn that has a valid embedding and is
            # above the minimum-duration threshold
            best_idx = -1
            best_dur = -1.0
            for i, seg in enumerate(segments):
                dur = seg["end"] - seg["start"]
                if turn_embeddings[i] is None:
                    continue
                if dur < self.min_enrollment_duration:
                    continue
                if dur > best_dur:
                    best_dur = dur
                    best_idx = i
            if best_idx < 0:
                # No qualifying turn yet — keep pyannote labels as-is
                logger.info(
                    "[DIARIZATION][ENROLL] session=%s no turn >=%.2fs with "
                    "valid embedding; deferring primary enrollment",
                    session_key, self.min_enrollment_duration,
                )
                return segments

            primary_embedding = turn_embeddings[best_idx]
            self._primary_embeddings[session_key] = primary_embedding
            logger.info(
                "[DIARIZATION][ENROLL] session=%s enrolled primary speaker "
                "from turn [%.2fs-%.2fs] duration=%.2fs (pyannote label=%s)",
                session_key,
                segments[best_idx]["start"], segments[best_idx]["end"],
                best_dur, segments[best_idx]["speaker"],
            )

        # Relabel every turn by similarity to the enrolled primary
        for i, seg in enumerate(segments):
            emb = turn_embeddings[i]
            if emb is None:
                # Too short to embed → inherit primary (avoid false rejects)
                new_label = "SPEAKER_00"
                sim = float("nan")
            else:
                sim = self._cosine(emb, primary_embedding)
                new_label = (
                    "SPEAKER_00" if sim >= self.voice_match_threshold else "SPEAKER_01"
                )
            logger.info(
                "[DIARIZATION][MATCH] session=%s turn [%.2fs-%.2fs] "
                "pyannote=%s cos_sim=%.3f threshold=%.2f -> %s",
                session_key,
                seg["start"], seg["end"], seg["speaker"], sim,
                self.voice_match_threshold, new_label,
            )
            seg["speaker"] = new_label

        return segments
