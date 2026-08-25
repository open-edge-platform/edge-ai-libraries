import logging
import os
import time
from unittest.mock import patch
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


def _is_gpu_tagged_storage_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "torch.storage.untypedstorage" in text and "tagged with gpu" in text


def _load_pipeline_with_map_location_fallback(
    pipeline_source: str,
    hf_token: str | None,
) -> Pipeline:
    try:
        return Pipeline.from_pretrained(pipeline_source, token=hf_token)
    except RuntimeError as exc:
        if not _is_gpu_tagged_storage_error(exc):
            raise

        logger.warning(
            "Detected GPU-tagged torch storage during pyannote load; retrying with map_location='cpu'"
        )
        original_torch_load = torch.load

        def _torch_load_cpu_first(*args, **kwargs):
            kwargs.setdefault("map_location", "cpu")
            return original_torch_load(*args, **kwargs)

        with patch("torch.load", side_effect=_torch_load_cpu_first):
            return Pipeline.from_pretrained(pipeline_source, token=hf_token)


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
            self.pipeline = _load_pipeline_with_map_location_fallback(
                pipeline_source,
                hf_token,
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
        # session_id → monotonic timestamp of last use (for TTL eviction)
        self._enrollment_last_used: dict[str, float] = {}
        self.enrollment_ttl_seconds = float(
            getattr(diar_cfg, "enrollment_ttl_seconds", 1800.0)
        )
        # Minimum span used to classify a speaker. Embeddings computed on much
        # less audio than this are unstable, so words are grouped into windows
        # of at least this length before comparison.
        self.min_window_seconds = float(
            getattr(diar_cfg, "min_window_seconds", 0.8)
        )
        # Span taken from the start of the first qualifying segment when
        # enrolling the primary voice.
        self.enrollment_window_seconds = float(
            getattr(diar_cfg, "enrollment_window_seconds", 1.5)
        )
        # How many words either side of a window-derived boundary to search
        # when snapping it to the nearest pause.
        self.boundary_search_words = int(
            getattr(diar_cfg, "boundary_search_words", 3)
        )

    def reset_enrollment(self, session_id: str | None = None) -> None:
        """Drop enrolled primary speaker embedding(s).

        If ``session_id`` is provided, only that session's enrollment is
        cleared. Otherwise all enrollments are dropped.
        """
        if session_id is None:
            self._primary_embeddings.clear()
            self._enrollment_last_used.clear()
        else:
            self._primary_embeddings.pop(session_id, None)
            self._enrollment_last_used.pop(session_id, None)

    def _evict_stale_enrollments(self) -> None:
        """Drop enrolled voices unused for longer than the TTL.

        The enrollment cache is keyed on a conversation id that lives as long as
        the browser tab, so without eviction the process would accumulate one
        embedding per customer indefinitely.
        """
        if self.enrollment_ttl_seconds <= 0:
            return
        now = time.monotonic()
        stale = [
            key
            for key, last in self._enrollment_last_used.items()
            if now - last > self.enrollment_ttl_seconds
        ]
        for key in stale:
            self._primary_embeddings.pop(key, None)
            self._enrollment_last_used.pop(key, None)
        if stale:
            logger.info(
                "[DIARIZATION][ENROLL] evicted %d stale enrollment(s) after %.0fs idle",
                len(stale), self.enrollment_ttl_seconds,
            )

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

    def _speaker_windows(self, words: list[dict]) -> list[list[int]]:
        """Group word indices into windows long enough to embed reliably.

        A speaker embedding needs roughly a second of audio to be stable, so
        individual words are too short to classify on their own. Words are
        accumulated until the window spans ``min_window_seconds``.

        Args:
            words: word dicts with ``start`` and ``end`` in chunk-local seconds.

        Returns:
            Lists of indices into ``words``, in order, covering every word.
        """
        windows: list[list[int]] = []
        current: list[int] = []
        for index, word in enumerate(words):
            current.append(index)
            span = float(words[current[-1]]["end"]) - float(words[current[0]]["start"])
            if span >= self.min_window_seconds:
                windows.append(current)
                current = []
        if current:
            # Trailing words too short to stand alone: merge into the previous
            # window rather than classifying them on insufficient audio.
            if windows:
                windows[-1].extend(current)
            else:
                windows.append(current)
        return windows

    def _refine_boundary(
        self, words: list[dict], verdicts: list[str]
    ) -> list[str]:
        """Snap each speaker-change boundary to the nearest pause.

        Verdicts are computed per window, so a boundary initially lands on a
        window edge and can misattribute the words around it. A real speaker
        change is almost always preceded by a silence, so each boundary is
        moved to the largest inter-word gap in its neighbourhood. This costs no
        extra embeddings.

        Args:
            words: word dicts with ``start``/``end``, in order.
            verdicts: per-word speaker labels to refine, same length as
                ``words``.

        Returns:
            A new verdict list with boundaries snapped to pauses.
        """
        refined = list(verdicts)
        for index in range(1, len(refined)):
            if refined[index] == refined[index - 1]:
                continue
            search_start = max(1, index - self.boundary_search_words)
            search_end = min(len(refined), index + self.boundary_search_words + 1)
            best_index = index
            best_gap = float(words[index]["start"]) - float(words[index - 1]["end"])
            for candidate in range(search_start, search_end):
                gap = float(words[candidate]["start"]) - float(words[candidate - 1]["end"])
                if gap > best_gap:
                    best_gap = gap
                    best_index = candidate
            if best_index == index:
                continue
            new_label = refined[index]
            if best_index < index:
                # Boundary moves earlier: words in between belong to the later
                # speaker after all.
                for position in range(best_index, index):
                    refined[position] = new_label
            else:
                previous_label = refined[index - 1]
                for position in range(index, best_index):
                    refined[position] = previous_label
        return refined

    def _split_segment_by_voice(
        self,
        segment: dict,
        waveform: torch.Tensor,
        sample_rate: int,
        primary_embedding: np.ndarray,
        session_key: str,
    ) -> list[dict]:
        """Split one Whisper segment wherever the speaking voice changes.

        Boundaries are derived by embedding successive word-aligned windows and
        comparing each to the enrolled primary voice. pyannote's own clustering
        is deliberately not used: on single-mic kiosk audio it routinely merges
        two co-located speakers into a single turn, which would leave a
        mixed-speaker segment unsplit.

        Args:
            segment: Whisper segment with ``words`` word-level timings.
            waveform: ``(channel, time)`` float32 tensor for the whole chunk.
            sample_rate: sample rate of ``waveform``.
            primary_embedding: L2-normalized enrolled reference voice.
            session_key: enrollment scope, for logging only.

        Returns:
            One sub-segment per contiguous run of same-speaker words, each
            carrying a ``speaker`` label. Falls back to a single labelled
            segment when word timings are unavailable.
        """
        words = segment.get("words") or []
        if not words:
            similarity = self._segment_similarity(
                waveform, sample_rate, segment, primary_embedding
            )
            labelled = dict(segment)
            labelled["speaker"] = self._label_for(similarity)
            return [labelled]

        verdicts: list[str] = [""] * len(words)
        for window in self._speaker_windows(words):
            start_s = float(words[window[0]]["start"])
            end_s = float(words[window[-1]]["end"])
            embedding = self._extract_embedding(waveform, sample_rate, start_s, end_s)
            if embedding is None:
                # Unembeddable window inherits the previous verdict so it can
                # never manufacture a speaker change on weak evidence.
                verdict = verdicts[window[0] - 1] if window[0] > 0 else "SPEAKER_00"
                similarity = float("nan")
            else:
                similarity = self._cosine(embedding, primary_embedding)
                verdict = self._label_for(similarity)
            logger.info(
                "[DIARIZATION][MATCH] session=%s window [%.2fs-%.2fs] "
                "cos_sim=%.3f threshold=%.2f -> %s",
                session_key, start_s, end_s, similarity,
                self.voice_match_threshold, verdict,
            )
            for index in window:
                verdicts[index] = verdict

        groups: list[dict] = []
        verdicts = self._refine_boundary(words, verdicts)
        for index, word in enumerate(words):
            verdict = verdicts[index]
            if groups and groups[-1]["speaker"] == verdict:
                groups[-1]["words"].append(word)
            else:
                groups.append({"speaker": verdict, "words": [word]})

        sub_segments: list[dict] = []
        for group in groups:
            group_words = group["words"]
            text = "".join(w.get("word", "") for w in group_words).strip()
            if not text:
                continue
            sub = dict(segment)
            sub["start"] = float(group_words[0]["start"])
            sub["end"] = float(group_words[-1]["end"])
            sub["text"] = text
            sub["words"] = group_words
            sub["speaker"] = group["speaker"]
            if len(groups) > 1:
                # Text rebuilt from word timings — caller re-applies the ASR
                # provider's repetition filter.
                sub["text_rebuilt"] = True
            sub_segments.append(sub)

        if not sub_segments:
            labelled = dict(segment)
            labelled["speaker"] = "SPEAKER_00"
            return [labelled]
        return sub_segments

    def _label_for(self, similarity: float) -> str:
        """Map a cosine similarity to a speaker label.

        Args:
            similarity: cosine similarity against the enrolled primary voice.
                ``NaN`` when no embedding could be computed.

        Returns:
            ``SPEAKER_00`` for the enrolled primary, else ``SPEAKER_01``.
            Unknown similarity resolves to primary so a real customer
            utterance is never dropped on missing evidence.
        """
        if not np.isfinite(similarity):
            return "SPEAKER_00"
        return "SPEAKER_00" if similarity >= self.voice_match_threshold else "SPEAKER_01"

    def _segment_similarity(
        self,
        waveform: torch.Tensor,
        sample_rate: int,
        segment: dict,
        primary_embedding: np.ndarray,
    ) -> float:
        """Cosine similarity of a whole segment against the enrolled voice."""
        embedding = self._extract_embedding(
            waveform, sample_rate,
            float(segment.get("start", 0.0)), float(segment.get("end", 0.0)),
        )
        if embedding is None:
            return float("nan")
        return self._cosine(embedding, primary_embedding)

    def _ensure_primary_embedding(
        self,
        waveform: torch.Tensor,
        sample_rate: int,
        segments: list[dict],
        session_key: str,
    ) -> np.ndarray | None:
        """Return the enrolled primary voice, enrolling it if necessary.

        Enrollment uses the earliest span long enough to embed: at a kiosk the
        customer speaks first, so first-speaker lock-on is the correct prior.
        The reference persists for the whole conversation — re-deriving it from
        each utterance would make every comparison a self-match.

        Args:
            waveform: ``(channel, time)`` float32 tensor.
            sample_rate: sample rate of ``waveform``.
            segments: Whisper segments for this chunk.
            session_key: conversation-scoped enrollment key.

        Returns:
            L2-normalized reference embedding, or ``None`` when this chunk has
            no span long enough to enroll from.
        """
        self._evict_stale_enrollments()
        existing = self._primary_embeddings.get(session_key)
        if existing is not None:
            self._enrollment_last_used[session_key] = time.monotonic()
            return existing

        for segment in segments:
            start_s = float(segment.get("start", 0.0))
            end_s = float(segment.get("end", 0.0))
            # Enroll from the opening of the first qualifying segment only.
            # Using the whole segment risks absorbing a bystander who starts
            # speaking partway through it.
            words = segment.get("words") or []
            if words:
                enroll_end = start_s
                for word in words:
                    enroll_end = float(word["end"])
                    if enroll_end - start_s >= self.enrollment_window_seconds:
                        break
                end_s = enroll_end
            else:
                end_s = min(end_s, start_s + self.enrollment_window_seconds)
            if end_s - start_s < self.min_enrollment_duration:
                continue
            embedding = self._extract_embedding(waveform, sample_rate, start_s, end_s)
            if embedding is None:
                continue
            self._primary_embeddings[session_key] = embedding
            self._enrollment_last_used[session_key] = time.monotonic()
            logger.info(
                "[DIARIZATION][ENROLL] session=%s enrolled primary speaker "
                "from [%.2fs-%.2fs] duration=%.2fs",
                session_key, start_s, end_s, end_s - start_s,
            )
            return embedding

        logger.info(
            "[DIARIZATION][ENROLL] session=%s no span >=%.2fs with a valid "
            "embedding; deferring enrollment",
            session_key, self.min_enrollment_duration,
        )
        return None

    def split_and_label_segments(
        self,
        audio_path: str,
        whisper_segments: list[dict],
        session_id: str | None = None,
    ) -> list[dict]:
        """Split Whisper segments at voice changes and label each part.

        Supersedes :meth:`label_whisper_segments`, which emitted at most one
        label per Whisper segment and so could not separate two speakers that
        Whisper had merged into a single segment.

        Args:
            audio_path: path to the chunk WAV.
            whisper_segments: Whisper segments, including ``words`` when the
                ASR provider supplies word-level timings.
            session_id: enrollment scope key. Must be stable for the whole
                conversation, otherwise the reference voice is re-derived from
                the audio being judged and every comparison degenerates to a
                self-match.

        Returns:
            Sub-segments each carrying a ``speaker`` field (``SPEAKER_00`` =
            enrolled primary). Length may exceed ``whisper_segments``. On any
            failure the input is returned unchanged — diarization must never
            break transcription.
        """
        if not self.voice_enrollment_enabled or not whisper_segments:
            return whisper_segments
        try:
            started = time.monotonic()
            session_key = session_id or "__default__"
            waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
            waveform_tensor = torch.from_numpy(np.ascontiguousarray(waveform.T))

            primary_embedding = self._ensure_primary_embedding(
                waveform_tensor, sample_rate, whisper_segments, session_key
            )
            if primary_embedding is None:
                return whisper_segments

            sub_segments: list[dict] = []
            for segment in whisper_segments:
                sub_segments.extend(
                    self._split_segment_by_voice(
                        segment, waveform_tensor, sample_rate,
                        primary_embedding, session_key,
                    )
                )
            logger.info(
                "[DIARIZATION] session=%s voice split %d whisper segment(s) into "
                "%d sub-segment(s) elapsed=%.0fms",
                session_key, len(whisper_segments), len(sub_segments),
                (time.monotonic() - started) * 1000.0,
            )
            return sub_segments
        except Exception as exc:
            logger.warning(
                "[DIARIZATION] split-and-label failed (%s); "
                "falling back to caller-provided labels", exc, exc_info=True,
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
        self._evict_stale_enrollments()
        self._enrollment_last_used[session_key] = time.monotonic()

        # Compute embeddings for every turn upfront (cache for reuse)
        turn_embeddings: list[np.ndarray | None] = [
            self._extract_embedding(waveform, sample_rate, s["start"], s["end"])
            for s in segments
        ]

        primary_embedding = self._primary_embeddings.get(session_key)
        if primary_embedding is None:
            # Enroll on the EARLIEST qualifying turn, not the longest: at a
            # kiosk the customer speaks first, so first-speaker lock-on is the
            # correct prior. Picking the longest turn would enrol a bystander
            # who happened to talk for longer in the opening chunk.
            best_idx = -1
            for i, seg in enumerate(segments):
                dur = seg["end"] - seg["start"]
                if turn_embeddings[i] is None:
                    continue
                if dur < self.min_enrollment_duration:
                    continue
                best_idx = i
                break
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
                segments[best_idx]["end"] - segments[best_idx]["start"],
                segments[best_idx]["speaker"],
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
