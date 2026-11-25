# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Per-request speaker options: whole-file diarization and known-speaker profiles.

Everything here is opt-in. A request that sets none of these fields (and a
deployment that keeps ``models.diarization.mode: chunk``) keeps the per-chunk
diarization and primary-speaker behaviour used by kiosk clients.

A speaker profile is a label plus a voice embedding from
``POST /v1/audio/speaker-embedding`` (same diarization model). After
diarization, each detected speaker's embedding is compared with the profiles by
cosine similarity and assigned one-to-one, best match first; speakers below the
threshold get ``unknown_speaker_label``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

DIARIZATION_MODES = ("chunk", "file")
MAX_PROFILES = 32
MAX_EMBEDDING_DIM = 4096
MAX_LABEL_LENGTH = 64
MAX_SPEAKERS = 20
DEFAULT_MATCH_THRESHOLD = 0.5


class SpeakerProfileError(ValueError):
    """A request's speaker options or profiles are invalid."""


@dataclass(frozen=True)
class SpeakerProfile:
    label: str
    embedding: np.ndarray  # L2-normalized


@dataclass
class SpeakerOptions:
    mode: str = "chunk"
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    profiles: list[SpeakerProfile] = field(default_factory=list)
    unknown_label: str | None = None
    match_threshold: float = DEFAULT_MATCH_THRESHOLD

    @property
    def file_mode(self) -> bool:
        return self.mode == "file"

    @property
    def labels_requested(self) -> bool:
        """Segments get ``speaker_label`` only when the caller asked for labels."""
        return bool(self.profiles) or self.unknown_label is not None

    @property
    def primary_label(self) -> str | None:
        """The first profile's label: segments matched to it are ``is_primary``."""
        return self.profiles[0].label if self.profiles else None


def unit_vector(values) -> np.ndarray | None:
    """L2-normalized float32 copy; None for empty, non-finite or zero vectors."""
    vector = np.asarray(values, dtype=np.float32).reshape(-1)
    if vector.size == 0 or not np.isfinite(vector).all():
        return None
    norm = float(np.linalg.norm(vector))
    if norm < 1e-8:
        return None
    return vector / norm


def _clean_label(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpeakerProfileError(f"{what} must be a non-empty string")
    label = value.strip()
    if len(label) > MAX_LABEL_LENGTH:
        raise SpeakerProfileError(f"{what} is longer than {MAX_LABEL_LENGTH} characters")
    return label


def parse_speaker_profiles(raw: str | None) -> list[SpeakerProfile]:
    """``[{"label": "Doctor", "embedding": [...]}, ...]`` (a JSON string) into profiles."""
    if raw is None or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SpeakerProfileError("speaker_profiles is not valid JSON") from exc
    if not isinstance(data, list):
        raise SpeakerProfileError("speaker_profiles must be a JSON array")
    if len(data) > MAX_PROFILES:
        raise SpeakerProfileError(f"speaker_profiles allows at most {MAX_PROFILES} entries")

    profiles: list[SpeakerProfile] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise SpeakerProfileError(f"speaker_profiles[{index}] must be an object")
        label = _clean_label(item.get("label"), f"speaker_profiles[{index}].label")
        values = item.get("embedding")
        if (
            not isinstance(values, list)
            or not values
            or len(values) > MAX_EMBEDDING_DIM
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
        ):
            raise SpeakerProfileError(
                f"speaker_profiles[{index}].embedding must be a list of 1-{MAX_EMBEDDING_DIM} numbers"
            )
        vector = unit_vector(values)
        if vector is None:
            raise SpeakerProfileError(f"speaker_profiles[{index}].embedding must be finite and non-zero")
        profiles.append(SpeakerProfile(label=label, embedding=vector))

    dims = {p.embedding.shape[0] for p in profiles}
    if len(dims) > 1:
        raise SpeakerProfileError("speaker_profiles embeddings must all have the same length")
    return profiles


def _speaker_count(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    if not 1 <= int(value) <= MAX_SPEAKERS:
        raise SpeakerProfileError(f"{name} must be between 1 and {MAX_SPEAKERS}")
    return int(value)


def build_speaker_options(
    *,
    configured_mode: str | None,
    configured_threshold: float | None,
    voice_enrollment_enabled: bool,
    mode: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    speaker_profiles: str | None = None,
    unknown_speaker_label: str | None = None,
    speaker_match_threshold: float | None = None,
) -> SpeakerOptions | None:
    """Validated options, or None when the request uses the default chunk behaviour."""
    requested_mode = (mode or "").strip().lower() or None
    effective_mode = requested_mode or (configured_mode or "chunk").strip().lower()
    if effective_mode not in DIARIZATION_MODES:
        raise SpeakerProfileError(f"diarization_mode must be one of: {', '.join(DIARIZATION_MODES)}")

    profiles = parse_speaker_profiles(speaker_profiles)
    unknown_label = (
        None
        if unknown_speaker_label is None or not unknown_speaker_label.strip()
        else _clean_label(unknown_speaker_label, "unknown_speaker_label")
    )
    counts = {
        "num_speakers": _speaker_count(num_speakers, "num_speakers"),
        "min_speakers": _speaker_count(min_speakers, "min_speakers"),
        "max_speakers": _speaker_count(max_speakers, "max_speakers"),
    }

    nothing_requested = (
        requested_mode is None
        and not profiles
        and unknown_label is None
        and speaker_match_threshold is None
        and all(v is None for v in counts.values())
    )
    if nothing_requested and effective_mode == "chunk":
        return None

    if any(v is not None for v in counts.values()) and effective_mode != "file":
        raise SpeakerProfileError("num_speakers, min_speakers and max_speakers need diarization_mode=file")
    if counts["num_speakers"] is not None and (counts["min_speakers"] or counts["max_speakers"]):
        raise SpeakerProfileError("Use either num_speakers or min_speakers/max_speakers, not both")
    if counts["min_speakers"] and counts["max_speakers"] and counts["min_speakers"] > counts["max_speakers"]:
        raise SpeakerProfileError("min_speakers must not exceed max_speakers")
    # Per-segment voice enrollment relabels speakers without per-speaker embeddings.
    if profiles and effective_mode == "chunk" and voice_enrollment_enabled:
        raise SpeakerProfileError("speaker_profiles need diarization_mode=file when voice enrollment is enabled")

    threshold = speaker_match_threshold
    if threshold is None:
        threshold = DEFAULT_MATCH_THRESHOLD if configured_threshold is None else configured_threshold
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise SpeakerProfileError("speaker_match_threshold must be between 0 and 1")

    return SpeakerOptions(
        mode=effective_mode,
        profiles=profiles,
        unknown_label=unknown_label,
        match_threshold=threshold,
        **counts,
    )


def match_speakers(
    label_embeddings: dict[str, np.ndarray],
    profiles: list[SpeakerProfile],
    threshold: float,
) -> dict[str, tuple[str, float]]:
    """Assign profile labels to diarized speakers: ``{speaker: (label, similarity)}``.

    Several profiles may share a label (more than one sample of one person); a
    speaker's similarity to a label is its best similarity to any of them. Each
    label goes to at most one speaker and each speaker gets at most one label,
    highest similarity first, and only at or above ``threshold``.
    """
    if not label_embeddings or not profiles:
        return {}

    by_label: dict[str, list[np.ndarray]] = {}
    for profile in profiles:
        by_label.setdefault(profile.label, []).append(profile.embedding)
    profile_dim = profiles[0].embedding.shape[0]

    candidates: list[tuple[float, str, str]] = []
    for speaker, embedding in label_embeddings.items():
        vector = unit_vector(embedding)
        if vector is None:
            continue
        if vector.shape[0] != profile_dim:
            raise SpeakerProfileError(
                f"speaker_profiles embeddings have {profile_dim} values but the diarization model "
                f"produces {vector.shape[0]}; create them with POST /v1/audio/speaker-embedding"
            )
        for label, vectors in by_label.items():
            similarity = max(float(np.dot(vector, v)) for v in vectors)
            candidates.append((similarity, speaker, label))

    matches: dict[str, tuple[str, float]] = {}
    used_labels: set[str] = set()
    for similarity, speaker, label in sorted(candidates, key=lambda c: c[0], reverse=True):
        if similarity < threshold:
            break
        if speaker in matches or label in used_labels:
            continue
        matches[speaker] = (label, similarity)
        used_labels.add(label)
    return matches
