import os
import logging
import math
from typing import Dict, Any, List

from components.asr.base_asr import BaseASR
from utils.config_loader import config

logger = logging.getLogger(__name__)


class WhisperCpp(BaseASR):
    def __init__(self, model_name="whisper-small", device="cpu", revision=None):
        try:
            from pywhispercpp.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "pywhispercpp is not installed. Run: pip install pywhispercpp"
            ) from exc

        from utils.ensure_model import get_asr_model_path, get_whispercpp_model_filename
        model_dir = get_asr_model_path()
        model_file = get_whispercpp_model_filename(
            model_name,
            getattr(config.models.asr, "weight_format", None),
        )
        model_path = os.path.join(model_dir, model_file)

        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"whisper.cpp model not found at {model_path}. "
                "Run ensure_model() or download manually."
            )

        if str(device).upper() != "CPU":
            logger.warning(
                "whispercpp backend only supports CPU in this service; overriding requested device %s -> CPU",
                device,
            )

        configured_threads = int(getattr(config.models.asr, "threads", 4) or 0)
        n_threads = configured_threads if configured_threads > 0 else max(1, os.cpu_count() or 1)
        self.beam_size = max(1, int(getattr(config.models.asr, "beam_size", 5) or 1))
        self.best_of = max(1, int(getattr(config.models.asr, "best_of", 5) or 1))
        self.word_timestamps = getattr(config.models.asr, "word_timestamps", False)
        self.repetition_penalty = getattr(config.models.asr, "repetition_penalty", 1.0)
        logger.info(f"Loading whisper.cpp model: {model_path} (threads={n_threads})")

        self.model = Model(
            model_path,
            params_sampling_strategy=1 if self.beam_size and self.beam_size > 1 else 0,
            n_threads=n_threads,
            print_realtime=False,
            print_progress=False,
        )
        self.n_threads = n_threads
        self.model_name = model_name

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
        probability = getattr(seg, "probability", None)
        if (not log_probs) and isinstance(probability, (int, float)) and probability > 0.0:
            avg_logprob = math.log(min(float(probability), 1.0))

        # Prefer a direct no_speech_prob field if pywhispercpp exposes it,
        # otherwise approximate from the first token's ptsum (timestamp-prob sum).
        no_speech_prob: float = getattr(seg, "no_speech_prob", None)  # type: ignore[assignment]
        if no_speech_prob is None and tokens:
            first = tokens[0]
            no_speech_prob = getattr(first, "ptsum", 0.0)
        if no_speech_prob is None:
            no_speech_prob = 0.0

        return avg_logprob, no_speech_prob

    def _remove_repeated_phrases(self, text: str) -> str:
        if not text or self.repetition_penalty <= 1.0:
            return text

        words = text.split()
        if len(words) < 2:
            return text

        result: List[str] = []
        index = 0
        while index < len(words):
            found_repeat = False
            max_window = min(8, (len(words) - index) // 2)
            for window in range(max_window, 0, -1):
                if words[index : index + window] == words[index + window : index + (2 * window)]:
                    result.extend(words[index : index + window])
                    index += 2 * window
                    found_repeat = True
                    break
            if not found_repeat:
                result.append(words[index])
                index += 1
        return " ".join(result)

    def _deduplicate_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.repetition_penalty <= 1.0:
            return segments

        deduped: List[Dict[str, Any]] = []
        previous_text: str | None = None
        for segment in segments:
            normalized = segment["text"].strip().lower()
            if normalized != previous_text:
                deduped.append(segment)
                previous_text = normalized
        return deduped

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
            "token_timestamps": self.word_timestamps,
            "extract_probability": True,
            "print_realtime": False,
            "print_progress": False,
            "no_context": True,
            "entropy_thold": 2.4,
            "logprob_thold": self.LOGPROB_THRESHOLD,
            "no_speech_thold": self.NO_SPEECH_THRESHOLD,
            "suppress_non_speech_tokens": True,
            "greedy": {"best_of": self.best_of},
            "beam_search": {"beam_size": self.beam_size, "patience": -1.0},
        }

        if language:
            transcribe_kwargs["language"] = language
        detected_language = language

        segments_raw = self.model.transcribe(audio_path, **transcribe_kwargs)

        segments: List[Dict[str, Any]] = []
        dropped = 0
        segments_total = 0

        for seg in segments_raw:
            segments_total += 1
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

        if dropped:
            logger.info(f"whispercpp: dropped {dropped} hallucination segment(s)")

        segments = self._deduplicate_segments(segments)
        for segment in segments:
            segment["text"] = self._remove_repeated_phrases(segment["text"])

        final_text = " ".join(segment["text"] for segment in segments).strip()
        final_text = self._remove_repeated_phrases(final_text)

        return {
            "text": final_text,
            "segments": segments,
            "language": detected_language,
            "meta": {
                "model": self.model_name,
                "temperature": temperature,
                "segments_total": segments_total,
                "segments_kept": len(segments),
                "segments_dropped": dropped,
            },
        }
