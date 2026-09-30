# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""FunASR Paraformer ASR provider (Chinese / English).

Optional provider selected via ``models.asr.provider: funasr``. It gives
higher-accuracy Chinese transcription than multilingual Whisper and also
supports English (``paraformer-en``). ``funasr`` and ``modelscope`` are
imported lazily inside ``__init__`` so importing this module never requires
those optional packages — the default image ships without them and existing
Whisper/OpenVINO consumers are unaffected.
"""
import logging
import os
import re

from components.asr.base_asr import BaseASR
from utils import ensure_model
from utils.config_loader import config
from utils.model_download_helper import get_or_download_model_dir

logger = logging.getLogger(__name__)

FUNASR_MODEL_MAP = {
    "paraformer-zh": "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "paraformer-en": "iic/speech_paraformer-large-vad-punc_asr_nat-en-16k-common-vocab10020",
    "paraformer-online": "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
}

# Language advertised in the transcription response, inferred from the model.
_MODEL_LANGUAGE = {
    "paraformer-zh": "zh",
    "paraformer-en": "en",
    "paraformer-online": "zh",
}

# Shared VAD + punctuation restoration models (used across Paraformer variants).
VAD_MODEL = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
PUNC_MODEL = "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"

_DEFAULT_REVISION = "v2.0.4"


def _is_empty_input_error(msg: str) -> bool:
    return "shapes cannot be multiplied" in msg and bool(re.search(r"\(\d+x0\b", msg))


def _resolve_hub() -> str:
    """Return the snapshot hub ("ms" or "hf") for FunASR model downloads.

    FunASR/iic models are published on ModelScope, so ModelScope is the
    default. Overridable via ``models.asr.model_hub`` (modelscope | huggingface).
    """
    raw = str(getattr(config.models.asr, "model_hub", "modelscope") or "modelscope").lower()
    return "hf" if raw in ("hf", "huggingface") else "ms"


class Paraformer(BaseASR):
    """FunASR Paraformer provider with integrated VAD and punctuation."""

    def __init__(self, model_name="paraformer-zh", device="cpu", revision=None):
        if model_name not in FUNASR_MODEL_MAP:
            raise ValueError(
                f"Invalid ASR model name {model_name}. "
                f"Supported models are: {list(FUNASR_MODEL_MAP.keys())}"
            )

        # funasr is an optional dependency (requirements-cjk.txt) — import here
        # so this module can be imported without it installed.
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "The FunASR Paraformer provider requires the optional Chinese-ASR "
                "dependencies. Install them with: pip install -r requirements-cjk.txt"
            ) from exc

        self.model_key = model_name
        self.language = _MODEL_LANGUAGE.get(model_name)
        revision = revision or _DEFAULT_REVISION
        hub = _resolve_hub()

        repo_id = FUNASR_MODEL_MAP[model_name]
        model_dir = ensure_model.get_asr_model_path()
        model_dir = get_or_download_model_dir(model=repo_id, hub=hub, revision=revision, local_dir=model_dir)

        model_dir_parent = os.path.dirname(model_dir)
        vad_model_dir = os.path.join(model_dir_parent, VAD_MODEL)
        vad_model_dir = get_or_download_model_dir(model=VAD_MODEL, hub=hub, revision=_DEFAULT_REVISION, local_dir=vad_model_dir)
        punc_model_dir = os.path.join(model_dir_parent, PUNC_MODEL)
        punc_model_dir = get_or_download_model_dir(model=PUNC_MODEL, hub=hub, revision=_DEFAULT_REVISION, local_dir=punc_model_dir)

        logger.info("Loading FunASR Paraformer model=%s on device=%s (hub=%s)", repo_id, device, hub)
        self.model_name = repo_id
        self.model = AutoModel(
            model=model_dir, model_revision=revision,
            vad_model=vad_model_dir, vad_model_revision=_DEFAULT_REVISION,
            punc_model=punc_model_dir, punc_model_revision=_DEFAULT_REVISION,
            device=device, disable_update=True,
        )

    def clean_text(self, text: str) -> str:
        """Repetition-filter hook (no-op for Paraformer; punctuation model handles output)."""
        return text

    def transcribe(self, audio_path: str, temperature: float = 0.0, language: str | None = None) -> dict:
        # `language` is accepted for interface parity with the Whisper providers;
        # the Paraformer model itself is language-specific (chosen via model name).
        try:
            res = self.model.generate(input=audio_path, sentence_timestamp=True, batch_size_s=300)

            if not res:
                return {"text": "", "segments": [], "language": self.language}

            out = res[0]
            segments = []
            for s in out.get("sentence_info", []):
                segments.append({
                    "start": s["start"] / 1000.0,  # ms -> seconds
                    "end": s["end"] / 1000.0,
                    "text": s["text"].strip(),
                })

            return {
                "text": out.get("text", "").strip(),
                "segments": segments,
                "language": self.language,
            }

        except Exception as exc:
            if _is_empty_input_error(str(exc)):
                logger.info("[ASR] empty/silent audio chunk skipped: %s", audio_path)
            else:
                logger.error("[ASR] Paraformer transcription error: %s", exc)
            return {"text": "", "segments": [], "language": self.language}
