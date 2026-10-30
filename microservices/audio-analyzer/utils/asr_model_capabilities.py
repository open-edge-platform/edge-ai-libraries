"""Capability checks derived from an ASR model's identifier.

Kept separate from the ASR backends so callers (HTTP endpoints, the realtime
socket) can ask "may I forward a language hint to this model?" without
importing or loading an inference backend.
"""

from __future__ import annotations

ENGLISH_ONLY_SUFFIX = ".en"


def is_english_only_model(model_name: str | None) -> bool:
    """Return True when ``model_name`` is an English-only Whisper checkpoint.

    Whisper and distil-whisper mark English-only checkpoints with a ``.en``
    suffix (e.g. ``distil-whisper/distil-small.en``). Those models have no
    language token at all, and ``openvino_genai.WhisperPipeline`` raises
    ``"Cannot specify 'language' for not multilingual model."`` when any
    language hint is forwarded — not only a non-English one.

    Args:
        model_name: The resolved ASR model identifier, or ``None``.

    Returns:
        True when a language hint must be withheld from this model.
    """
    if not model_name:
        return False
    return str(model_name).strip().lower().endswith(ENGLISH_ONLY_SUFFIX)
