"""Kokoro-82M TTS via kokoro-onnx (onnxruntime, CPU).

Kokoro is MIT-licensed (package) and Apache-2.0 (model) and sounds close to a
human voice. It runs on the CPU through onnxruntime, so it is registered under
both the OpenVINO and PyTorch runtime lists and is selected purely by model
name (``kokoro``).
"""
import logging
import re
import threading

import numpy as np

from components.tts.base import BaseTTSService, TTSServiceConfig, model_name_matches
from components.tts.text_normalizer import normalize_for_speech
from utils.ensure_kokoro import ensure_kokoro, model_paths


logger = logging.getLogger(__name__)


IMPLEMENTATION_NAME = "kokoro"

_SAMPLE_RATE = 24000
_DEFAULT_VOICE = "af_heart"
# Kokoro is multilingual; the service only advertises English, spoken with the
# American English phoneme set.
_LANG = "en-us"
# Cap onnxruntime threads so Kokoro does not fight the rest of the pipeline for
# CPU cores (uncapped it slows its own decode loop).
_INTRA_OP_THREADS = 4

# Split into clauses on sentence/clause punctuation so streaming can emit one
# chunk per phrase.
_PHRASE_SPLIT = re.compile(r"(?<=[.!?,;:])\s+")


def matches_model_name(model_name: str) -> bool:
    return model_name_matches(model_name, "kokoro")


class KokoroTTSService(BaseTTSService):
    _models: dict = {}
    _lock = threading.Lock()

    def __init__(self, config: TTSServiceConfig):
        super().__init__(config)
        model_key = self._get_model_key(IMPLEMENTATION_NAME)
        with KokoroTTSService._lock:
            if model_key not in KokoroTTSService._models:
                KokoroTTSService._models[model_key] = self._load_model()
        self.k = KokoroTTSService._models[model_key]
        self._inference_lock = self._get_inference_lock(IMPLEMENTATION_NAME)
        self.sample_rate = _SAMPLE_RATE

    def _load_model(self):
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:
            raise RuntimeError(
                "kokoro-onnx is not installed. Install requirements.txt before starting the service."
            ) from exc

        model_path, voices_path = ensure_kokoro()
        try:
            import onnxruntime as ort

            session_options = ort.SessionOptions()
            session_options.intra_op_num_threads = _INTRA_OP_THREADS
            session = ort.InferenceSession(model_path, session_options)
            return Kokoro.from_session(session, voices_path)
        except Exception:
            logger.warning("Falling back to default Kokoro session (thread cap not applied)", exc_info=True)
            return Kokoro(model_path, voices_path)

    def _supported_voices(self) -> list[str]:
        try:
            return sorted(self.k.get_voices())
        except Exception:
            return [_DEFAULT_VOICE]

    def _resolve_kokoro_voice(self, speaker: str | None) -> str:
        requested = (speaker or self.config.default_speaker or _DEFAULT_VOICE).strip()
        available = set(self._supported_voices())
        if not available or requested in available:
            return requested
        # The orchestrator configures a single voice name globally, which may be
        # a voice from another model (e.g. SpeechT5's "Ryan"). Fall back to the
        # Kokoro default instead of failing the whole utterance.
        fallback = self.config.default_speaker if self.config.default_speaker in available else _DEFAULT_VOICE
        if fallback not in available:
            fallback = next(iter(sorted(available)))
        logger.warning("[KOKORO] Unknown voice %r; falling back to %r", requested, fallback)
        return fallback

    def synthesize(
        self,
        text: str,
        language: str | None = None,
        speaker: str | None = None,
        instructions: str | None = None,
    ) -> dict:
        normalized_text = self._validate_text(text)
        spoken_text = normalize_for_speech(normalized_text)
        if not spoken_text:
            raise ValueError("Input text contains no pronounceable characters")
        if spoken_text != normalized_text:
            logger.debug("[KOKORO] Normalised text for synthesis: %r -> %r", normalized_text, spoken_text)

        chosen_language, chosen_speaker = self._resolve_voice_request(language, speaker)
        if instructions:
            raise ValueError("Kokoro does not support free-form voice instructions.")

        voice = self._resolve_kokoro_voice(chosen_speaker)
        with self._inference_lock:
            audio, sample_rate = self.k.create(spoken_text, voice=voice, speed=1.0, lang=_LANG)
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        return self._build_result(audio, sample_rate, voice, chosen_language, instructions)

    def synthesize_stream(
        self,
        text: str,
        language: str | None = None,
        speaker: str | None = None,
        instructions: str | None = None,
    ):
        normalized_text = self._validate_text(text)
        if not normalize_for_speech(normalized_text):
            raise ValueError("Input text contains no pronounceable characters")
        chosen_language, chosen_speaker = self._resolve_voice_request(language, speaker)
        if instructions:
            raise ValueError("Kokoro does not support free-form voice instructions.")
        voice = self._resolve_kokoro_voice(chosen_speaker)

        phrases = [p.strip() for p in _PHRASE_SPLIT.split(normalized_text) if p.strip()]
        for phrase in phrases:
            spoken = normalize_for_speech(phrase)
            if not spoken:
                continue
            with self._inference_lock:
                audio, sample_rate = self.k.create(spoken, voice=voice, speed=1.0, lang=_LANG)
            audio = np.asarray(audio, dtype=np.float32).reshape(-1)
            yield self._build_result(audio, sample_rate, voice, chosen_language, instructions)

    def get_model_info(self) -> dict:
        info = self._build_model_info(IMPLEMENTATION_NAME, self.k)
        info["supported_languages"] = [self.config.default_language]
        info["supported_speakers"] = self._supported_voices()
        return info


def create_service(config: TTSServiceConfig):
    return KokoroTTSService(config)
