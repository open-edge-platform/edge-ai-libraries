# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""FunASR Paraformer ASR provider (Chinese / English).

Optional provider selected via ``models.asr.provider: funasr``. It gives
higher-accuracy Chinese transcription than multilingual Whisper and also
supports English (``paraformer-en``). ``funasr`` is imported lazily inside ``__init__`` so
importing this module never requires the optional dependencies — the default
image ships without them and existing Whisper/OpenVINO consumers are unaffected.
"""
import logging
import re

from components.asr.base_asr import BaseASR
from utils.config_loader import config
from utils.model_download_client import get_model_from_service

logger = logging.getLogger(__name__)

FUNASR_MODEL_MAP = {
    "paraformer-zh": "funasr/paraformer-zh",
    "paraformer-en": "funasr/paraformer-en",
    "paraformer-online": "funasr/paraformer-zh-streaming",
}

# Language advertised in the transcription response, inferred from the model.
_MODEL_LANGUAGE = {
    "paraformer-zh": "zh",
    "paraformer-en": "en",
    "paraformer-online": "zh",
}

# Shared VAD + punctuation restoration models (used across Paraformer variants).
# Overridable via models.asr.vad_model / models.asr.punc_model; the defaults are
# the canonical FunASR companion models.
VAD_MODEL = str(getattr(config.models.asr, "vad_model", None)
                or "funasr/fsmn-vad")
PUNC_MODEL = str(getattr(config.models.asr, "punc_model", None)
                 or "funasr/ct-punc")

_MODEL_REVISIONS = {
    "funasr/paraformer-zh": "d7811ee3ac581fbcfdeb37c98c6ba674028433dc",
    "funasr/paraformer-en": "2bad1d78c117f38172165dccbc4575df6277ee0a",
    "funasr/paraformer-zh-streaming": "fd2af606b37d7fb8b3b8a218c5be5b07b53ef6ba",
    "funasr/fsmn-vad": "df20e6b30c653645fa4ff125cacfcabd1020a669",
    "funasr/ct-punc": "d0e55e2b8722a78b63705ff443d09c4f86e5d750",
}


def _is_empty_input_error(msg: str) -> bool:
    return "shapes cannot be multiplied" in msg and bool(re.search(r"\(\d+x0\b", msg))


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
        repo_id = FUNASR_MODEL_MAP[model_name]
        revision = revision or _MODEL_REVISIONS[repo_id]
        required_files = ["config.yaml", "model.pt"]
        model_dir = get_model_from_service(
            repo_id, revision, hub="huggingface", required_files=required_files,
        )
        vad_model_dir = get_model_from_service(
            VAD_MODEL, _MODEL_REVISIONS.get(VAD_MODEL),
            hub="huggingface", required_files=required_files,
        )
        punc_model_dir = get_model_from_service(
            PUNC_MODEL, _MODEL_REVISIONS.get(PUNC_MODEL),
            hub="huggingface", required_files=required_files,
        )

        logger.info("Loading FunASR Paraformer model=%s on device=%s (hub=huggingface)", repo_id, device)
        self.model_name = repo_id
        self.model = AutoModel(
            model=model_dir,
            vad_model=vad_model_dir,
            punc_model=punc_model_dir,
            device=device, disable_update=True,
        )

    def clean_text(self, text: str) -> str:
        """Repetition-filter hook (no-op for Paraformer; punctuation model handles output)."""
        return text

    def transcribe(self, audio_path: str, temperature: float = 0.0, language: str | None = None) -> dict:
        # `language` is accepted for interface parity with the Whisper providers;
        # the Paraformer model itself is language-specific (chosen via model name).
        try:
            res = self.model.generate(
                input=audio_path, pred_timestamp=True,
                sentence_timestamp=True, batch_size_s=300,
            )

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
                logger.exception("[ASR] Paraformer transcription failed")
                raise
            return {"text": "", "segments": [], "language": self.language}
