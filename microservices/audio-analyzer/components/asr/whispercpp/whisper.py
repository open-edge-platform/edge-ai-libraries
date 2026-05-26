import os
import logging
from typing import Dict, Any, List

from components.asr.base_asr import BaseASR
from utils.config_loader import config

logger = logging.getLogger(__name__)

WHISPER_CPP_MODEL_MAP = {
    "whisper-tiny":   "ggml-tiny.bin",
    "whisper-base":   "ggml-base.bin",
    "whisper-small":  "ggml-small.bin",
    "whisper-medium": "ggml-medium.bin",
    "whisper-large":  "ggml-large-v3.bin",
}


class WhisperCpp(BaseASR):
    def __init__(self, model_name="whisper-small", device="cpu", revision=None):
        try:
            from pywhispercpp.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "pywhispercpp is not installed. Run: pip install pywhispercpp"
            ) from exc

        model_file = WHISPER_CPP_MODEL_MAP.get(model_name)
        if not model_file:
            raise ValueError(
                f"Unsupported whisper.cpp model name: '{model_name}'. "
                f"Valid names: {list(WHISPER_CPP_MODEL_MAP)}"
            )

        from utils.ensure_model import get_asr_model_path
        model_dir = get_asr_model_path()
        model_path = os.path.join(model_dir, model_file)

        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"whisper.cpp model not found at {model_path}. "
                "Run ensure_model() or download manually."
            )

        n_threads = getattr(config.models.asr, "threads", 4)
        logger.info(f"Loading whisper.cpp model: {model_path} (threads={n_threads})")

        self.model = Model(model_path, n_threads=n_threads)
        self.beam_size = getattr(config.models.asr, "beam_size", 5)
        self.best_of = getattr(config.models.asr, "best_of", 5)
        self.word_timestamps = getattr(config.models.asr, "word_timestamps", False)

        # Hallucination filter thresholds (same config keys as openai provider)
        self.NO_SPEECH_THRESHOLD = getattr(config.models.asr, "no_speech_threshold", 0.6)
        self.LOGPROB_THRESHOLD = getattr(config.models.asr, "logprob_threshold", -1.0)
        self.MIN_DURATION_SEC = getattr(config.models.asr, "min_duration_sec", 0.25)
        self.MIN_WORDS = getattr(config.models.asr, "min_words", 2)

    def _segment_stats(self, seg) -> tuple[float, float]:
        """
        Derive avg_logprob and no_speech_prob from pywhispercpp token data.

        pywhispercpp token fields:
          plog   — log probability of this token
          ptsum  — sum of timestamp-token probabilities for this position;
                   high ptsum means the model prefers a timestamp (silence/gap)
        """
        tokens = getattr(seg, "tokens", None) or []
        log_probs = [
            t.plog for t in tokens
            if hasattr(t, "plog")
            and t.plog != float("-inf")
            and getattr(t, "id", -1) >= 0
        ]
        avg_logprob = sum(log_probs) / len(log_probs) if log_probs else -1.0

        # Prefer a direct no_speech_prob field if pywhispercpp exposes it,
        # otherwise approximate from the first token's ptsum (timestamp-prob sum).
        no_speech_prob: float = getattr(seg, "no_speech_prob", None)  # type: ignore[assignment]
        if no_speech_prob is None and tokens:
            first = tokens[0]
            no_speech_prob = getattr(first, "ptsum", 0.0)
        if no_speech_prob is None:
            no_speech_prob = 0.0

        return avg_logprob, no_speech_prob

    def _is_hallucination(self, text: str, start: float, end: float,
                          avg_logprob: float, no_speech_prob: float) -> bool:
        """
        Mirror the same multi-signal logic as the openai backend.
        A segment is dropped only when ALL three conditions hold simultaneously.
        """
        # 1. Acoustically silence-like
        if no_speech_prob <= self.NO_SPEECH_THRESHOLD:
            return False
        # 2. Low model confidence
        if avg_logprob >= self.LOGPROB_THRESHOLD:
            return False
        # 3. Very short OR nearly empty
        duration = end - start
        if duration >= self.MIN_DURATION_SEC and len(text.split()) >= self.MIN_WORDS:
            return False
        return True

    def transcribe(self, audio_path: str, temperature: float = 0.0, language: str | None = None) -> Dict[str, Any]:
        transcribe_kwargs = {
            "temperature": temperature,
            "beam_size": self.beam_size,
            "best_of": self.best_of,
            "word_timestamps": self.word_timestamps,
        }
        if language:
            transcribe_kwargs["language"] = language

        try:
            segments_raw = self.model.transcribe(audio_path, **transcribe_kwargs)
        except TypeError:
            transcribe_kwargs.pop("language", None)
            segments_raw = self.model.transcribe(audio_path, **transcribe_kwargs)

        segments: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        dropped = 0

        for seg in segments_raw:
            text = seg.text.strip()
            if not text:
                continue
            # whisper.cpp reports t0/t1 in centiseconds (10 ms units)
            start = seg.t0 / 100.0
            end = seg.t1 / 100.0

            avg_logprob, no_speech_prob = self._segment_stats(seg)

            if self._is_hallucination(text, start, end, avg_logprob, no_speech_prob):
                dropped += 1
                logger.debug(
                    "whispercpp: dropped hallucination segment "
                    f"[{start:.2f}s–{end:.2f}s] no_speech={no_speech_prob:.3f} "
                    f"avg_logprob={avg_logprob:.3f} text={text!r}"
                )
                continue

            segments.append({
                "text": text,
                "start": start,
                "end": end,
                "avg_logprob": avg_logprob,
                "no_speech_prob": no_speech_prob,
            })
            text_parts.append(text)

        if dropped:
            logger.info(f"whispercpp: dropped {dropped} hallucination segment(s)")

        return {
            "text": " ".join(text_parts),
            "segments": segments,
        }
