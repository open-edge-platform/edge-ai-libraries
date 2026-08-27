"""Cross-chunk primary-speaker identity resolution.

Pyannote resets its anonymous speaker labels (``SPEAKER_00``, ``SPEAKER_01``,
...) on every diarization call, so the same physical person can receive a
different label in consecutive audio chunks. This module gives callers a
label that is *stable across chunks* for a given session, without loading any
additional model: it reuses the speaker embeddings the diarization pipeline
already computes internally during clustering
(``pyannote.audio.pipelines.speaker_diarization.DiarizeOutput.speaker_embeddings``).

Usage
-----
>>> store = SpeakerIdentityStore(similarity_threshold=0.75)
>>> primary_map = store.resolve(session_id, label_embeddings, turns)
>>> primary_map["SPEAKER_00"]  # True if this chunk's SPEAKER_00 is the locked primary
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class _SessionIdentity:
    """Per-session identity state kept in memory only (no persistence needed)."""

    primary_embedding: np.ndarray | None = None
    locked: bool = False
    last_seen: float = field(default_factory=time.monotonic)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class SpeakerIdentityStore:
    """Thread-safe, in-memory, per-session primary-speaker resolver.

    For each session, the first speaker turn that meets ``lock_min_duration_sec``
    freezes its embedding as the "primary" identity. Every subsequent chunk's
    speaker turns are compared against that frozen embedding via cosine
    similarity; matches above ``similarity_threshold`` are tagged primary,
    regardless of what anonymous label pyannote assigned them this time.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.75,
        lock_min_duration_sec: float = 0.75,
        session_ttl_seconds: float = 1800.0,
    ):
        self.similarity_threshold = similarity_threshold
        self.lock_min_duration_sec = lock_min_duration_sec
        self.session_ttl_seconds = session_ttl_seconds
        self._sessions: dict[str, _SessionIdentity] = {}
        self._lock = threading.Lock()

    def _evict_expired(self, now: float) -> None:
        expired = [
            session_id
            for session_id, state in self._sessions.items()
            if now - state.last_seen > self.session_ttl_seconds
        ]
        for session_id in expired:
            logger.info("[SPEAKER-IDENTITY] session=%s | evicted (idle TTL)", session_id)
            del self._sessions[session_id]

    @staticmethod
    def _turn_durations(turns: list[dict]) -> dict[str, float]:
        """Sum turn duration per speaker label for this chunk."""
        durations: dict[str, float] = {}
        for turn in turns:
            speaker = turn.get("speaker")
            if not speaker:
                continue
            durations[speaker] = durations.get(speaker, 0.0) + max(
                0.0, float(turn["end"]) - float(turn["start"])
            )
        return durations

    def resolve(
        self,
        session_id: str,
        label_embeddings: dict[str, np.ndarray],
        turns: list[dict],
    ) -> dict[str, bool]:
        """Return ``{label: is_primary}`` for this chunk's speaker labels.

        Args:
            session_id: Stable identifier for the audio session.
            label_embeddings: Mapping of this chunk's local speaker label
                (e.g. ``"SPEAKER_00"``) to its mean embedding, as produced by
                ``PyannoteDiarizer.diarize()``.
            turns: This chunk's speaker turns (``{start, end, speaker}``),
                used only to find the longest-speaking label when locking on.

        Returns:
            Mapping from each label in ``label_embeddings`` to whether it is
            resolved as the session's primary speaker.
        """
        if not label_embeddings:
            return {}

        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            state = self._sessions.setdefault(session_id, _SessionIdentity())
            state.last_seen = now

            if not state.locked:
                durations = self._turn_durations(turns)
                # Longest-speaking label this chunk, among those we have an
                # embedding for and that meets the minimum lock duration.
                candidate_label = None
                candidate_duration = 0.0
                for label, duration in durations.items():
                    if label not in label_embeddings:
                        continue
                    if duration < self.lock_min_duration_sec:
                        continue
                    if duration > candidate_duration:
                        candidate_duration = duration
                        candidate_label = label

                if candidate_label is None:
                    # Nothing met the lock threshold yet — every label in this
                    # chunk is provisionally "unresolved" (not primary).
                    logger.info(
                        "[SPEAKER-IDENTITY] session=%s | no candidate met lock_min_duration=%.2fs this chunk — "
                        "no primary resolved yet",
                        session_id, self.lock_min_duration_sec,
                    )
                    return {label: False for label in label_embeddings}

                state.primary_embedding = np.asarray(
                    label_embeddings[candidate_label], dtype=np.float32
                )
                state.locked = True
                logger.info(
                    "[SPEAKER-IDENTITY] session=%s | locked primary identity on label=%s (duration=%.2fs)",
                    session_id, candidate_label, candidate_duration,
                )

            primary_embedding = state.primary_embedding

        result: dict[str, bool] = {}
        for label, embedding in label_embeddings.items():
            similarity = _cosine_similarity(np.asarray(embedding, dtype=np.float32), primary_embedding)
            is_primary = similarity >= self.similarity_threshold
            result[label] = is_primary
            logger.info(
                "[SPEAKER-IDENTITY] session=%s | label=%s similarity=%.3f (threshold=%.2f) → is_primary=%s",
                session_id, label, similarity, self.similarity_threshold, is_primary,
            )
        return result

    def reset(self, session_id: str) -> None:
        """Drop stored identity state for a session (e.g. on session end)."""
        with self._lock:
            self._sessions.pop(session_id, None)
