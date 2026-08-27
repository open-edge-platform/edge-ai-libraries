"""Named speaker voices for SpeechT5.

SpeechT5 is speaker-conditioned: the acoustic model takes a 512-dimension
x-vector alongside the text, and that vector alone determines the timbre. When
no embedding is supplied, ``openvino_genai.Text2SpeechPipeline`` falls back to
vector 7306 of the ``Matthijs/cmu-arctic-xvectors`` validation split — a thin,
low-energy ``cmu_us_slt`` rendition that sounds feeble over kiosk speakers.

This module turns that implicit fallback into an explicit, named voice
registry. Each voice ships as a 512-float32 ``.npy`` under
``assets/speecht5_speakers/``, computed as the L2-normalised mean of 100
x-vectors for that CMU Arctic speaker. Averaging a speaker's vectors instead of
picking one utterance yields a more canonical timbre and avoids the
per-utterance artefacts that make single vectors sound unstable.

Voice names mirror the naming style Qwen3-TTS ``custom_voice`` uses so callers
see a consistent vocabulary across models. The underlying CMU Arctic speaker
ids are accepted as aliases.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np


EMBEDDING_DIM = 512

_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "speecht5_speakers"


@dataclass(frozen=True)
class SpeechT5Voice:
    """A named SpeechT5 voice backed by a bundled x-vector."""

    name: str
    speaker_id: str      # CMU Arctic speaker, also the asset file stem
    description: str


# Ordered registry — the first entry is the recommended kiosk default.
# Measured on the OpenVINO int8 CPU pipeline with a 2-sentence kiosk reply:
#   bdl 999 ms / 5.66 s audio / -29.5 dBFS   (loudest and fastest)
#   jmk 1143 ms / 6.40 s / -28.2 dBFS        (fullest, latency neutral)
#   clb 1342 ms / 7.39 s / -28.4 dBFS        (warmest, slower)
#   slt 1150 ms / 6.78 s / -33.3 dBFS        (the old implicit default)
_VOICES: tuple[SpeechT5Voice, ...] = (
    SpeechT5Voice("Ryan", "bdl", "US English male, bright and projecting"),
    SpeechT5Voice("Miles", "jmk", "Canadian English male, full and even"),
    SpeechT5Voice("Aaron", "rms", "US English male, deep and measured"),
    SpeechT5Voice("Nora", "clb", "US English female, warm and rounded"),
    SpeechT5Voice("Elena", "slt", "US English female, light and soft"),
    SpeechT5Voice("Kabir", "ksp", "Indian English male, crisp"),
    SpeechT5Voice("Angus", "awb", "Scottish English male, slow paced"),
)

DEFAULT_VOICE = _VOICES[0].name

_BY_KEY: dict[str, SpeechT5Voice] = {}
for _voice in _VOICES:
    _BY_KEY[_voice.name.lower()] = _voice
    _BY_KEY[_voice.speaker_id.lower()] = _voice

_cache: dict[str, np.ndarray] = {}
_cache_guard = threading.Lock()


def supported_speakers() -> list[str]:
    """Return the display names of every bundled voice, best first."""
    return [voice.name for voice in _VOICES]


def describe_speakers() -> list[dict[str, str]]:
    """Return name/speaker_id/description for every bundled voice."""
    return [
        {"name": voice.name, "speaker_id": voice.speaker_id, "description": voice.description}
        for voice in _VOICES
    ]


def is_supported(speaker: str | None) -> bool:
    """Return True when ``speaker`` names a bundled voice (or its CMU alias)."""
    return bool(speaker) and speaker.strip().lower() in _BY_KEY


def resolve_voice(speaker: str | None) -> SpeechT5Voice:
    """Resolve a requested voice name to its registry entry.

    Args:
        speaker: Voice display name (``"Ryan"``) or CMU Arctic id (``"bdl"``).

    Returns:
        The matching :class:`SpeechT5Voice`.

    Raises:
        ValueError: If the name is empty or not part of the registry.
    """
    key = (speaker or "").strip().lower()
    if not key:
        raise ValueError("SpeechT5 requires a speaker name.")
    voice = _BY_KEY.get(key)
    if voice is None:
        raise ValueError(
            f"Unsupported voice '{speaker}'. Supported voices: {', '.join(supported_speakers())}."
        )
    return voice


def load_embedding(speaker: str | None) -> np.ndarray:
    """Load the x-vector for a named voice as a ``(1, 512)`` float32 array.

    Embeddings are cached per speaker id; the arrays are returned read-only so
    a caller cannot mutate the shared cache entry.

    Args:
        speaker: Voice display name or CMU Arctic id.

    Returns:
        The speaker embedding shaped ``(1, EMBEDDING_DIM)``.

    Raises:
        ValueError: If the voice is unknown.
        RuntimeError: If the bundled asset is missing or malformed.
    """
    voice = resolve_voice(speaker)

    with _cache_guard:
        cached = _cache.get(voice.speaker_id)
        if cached is not None:
            return cached

        asset = _ASSET_DIR / f"{voice.speaker_id}.npy"
        if not asset.is_file():
            raise RuntimeError(
                f"Speaker embedding asset missing for voice '{voice.name}': {asset}"
            )

        embedding = np.load(asset).astype(np.float32).reshape(1, -1)
        if embedding.shape[1] != EMBEDDING_DIM:
            raise RuntimeError(
                f"Speaker embedding for '{voice.name}' has dimension {embedding.shape[1]}, "
                f"expected {EMBEDDING_DIM}."
            )
        embedding.setflags(write=False)
        _cache[voice.speaker_id] = embedding
        return embedding
