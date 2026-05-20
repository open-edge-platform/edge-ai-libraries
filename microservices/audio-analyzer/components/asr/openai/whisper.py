from components.asr.base_asr import BaseASR
import whisper
import logging
from utils.config_loader import config
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

WHISPER_MODEL_MAP = {
    "whisper-tiny": "tiny",
    "whisper-base": "base",
    "whisper-small": "small",
    "whisper-medium": "medium",
    "whisper-large": "large-v3",
}


class Whisper(BaseASR):
    """
    Robust Whisper ASR with silence-safe filtering.
    Prevents hallucinations without dropping real speech.
    """

    def __init__(self, model_name="whisper-small", device="cpu", revision=None):
        if model_name not in WHISPER_MODEL_MAP:
            raise ValueError(f"Invalid ASR model name: {model_name}")

        self.model_name = model_name
        model_id = WHISPER_MODEL_MAP[model_name]
        logger.info(f"Loading Whisper model={model_id} on device={device}")

        self.model = whisper.load_model(model_id, device=device)

        # ---- Conservative thresholds (DO NOT overtune) ----
        self.NO_SPEECH_THRESHOLD = config.models.asr.no_speech_threshold
        self.LOGPROB_THRESHOLD = config.models.asr.logprob_threshold
        self.MIN_DURATION_SEC = config.models.asr.min_duration_sec
        self.MIN_WORDS = config.models.asr.min_words
        # openai-whisper's DecodingOptions has no repetition_penalty field —
        # passing it as a kwarg raises TypeError.  Applied as post-processing.
        self.REPETITION_PENALTY = getattr(config.models.asr, "repetition_penalty", 1.0)
        # Native whisper param: skip generation over silent regions > N seconds.
        # null/None disables it.
        _hst = getattr(config.models.asr, "hallucination_silence_threshold", None)
        self.HALLUCINATION_SILENCE_THRESHOLD = float(_hst) if _hst is not None else None

    def _is_silent_segment(self, seg: Dict[str, Any]) -> bool:
        """
        Decide whether a segment is silence / hallucination.
        Uses MULTIPLE signals to avoid dropping real speech.
        """

        text = seg.get("text", "").strip()
        duration = float(seg["end"]) - float(seg["start"])
        no_speech_prob = seg.get("no_speech_prob", 0.0)
        avg_logprob = seg.get("avg_logprob", 0.0)

        # 1. Must be acoustically silence-like
        if no_speech_prob <= self.NO_SPEECH_THRESHOLD:
            return False

        # 2. Must be low confidence
        if avg_logprob >= self.LOGPROB_THRESHOLD:
            return False

        # 3. Must be very short or nearly empty
        if duration >= self.MIN_DURATION_SEC and len(text.split()) >= self.MIN_WORDS:
            return False

        return True

    def _remove_repeated_phrases(self, text: str) -> str:
        """
        Remove consecutive repeated word sequences (window 1-8 words).
        Only active when repetition_penalty > 1.0.
        """
        if not text or self.REPETITION_PENALTY <= 1.0:
            return text

        words = text.split()
        if len(words) < 2:
            return text

        result: List[str] = []
        i = 0
        while i < len(words):
            found = False
            max_window = min(8, (len(words) - i) // 2)
            for w in range(max_window, 0, -1):
                if words[i : i + w] == words[i + w : i + 2 * w]:
                    result.extend(words[i : i + w])
                    i += 2 * w
                    found = True
                    break
            if not found:
                result.append(words[i])
                i += 1
        return " ".join(result)

    def _deduplicate_segments(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Drop segments whose text is identical to the immediately preceding
        segment (common whisper loop artifact). Only active when
        repetition_penalty > 1.0.
        """
        if self.REPETITION_PENALTY <= 1.0:
            return segments

        deduped: List[Dict[str, Any]] = []
        prev_text: str | None = None
        for seg in segments:
            text = seg["text"].strip().lower()
            if text != prev_text:
                deduped.append(seg)
                prev_text = text
        return deduped

    def transcribe(self, audio_path: str, temperature: float = 0.0, language: str | None = None) -> Dict[str, Any]:
        """
        Transcribe audio with strong silence suppression and zero speech loss.
        """

        # no_speech_threshold and logprob_threshold are passed to whisper's
        # internal segment filter AND re-checked in _is_silent_segment() below.
        # Both layers read from the same config values so the behaviour is
        # consistent; the double-pass only affects segments whisper would have
        # kept but our stricter multi-signal check rejects.
        result = self.model.transcribe(
            audio_path,
            temperature=temperature,
            language=language,
            condition_on_previous_text=False,
            no_speech_threshold=self.NO_SPEECH_THRESHOLD,
            logprob_threshold=self.LOGPROB_THRESHOLD,

            # Repetition control (decoder level)
            beam_size=5,
            best_of=1,

            # Hallucination guard
            compression_ratio_threshold=2.4,

            # Skip generation over silent regions (mic noise fix)
            hallucination_silence_threshold=self.HALLUCINATION_SILENCE_THRESHOLD,

            verbose=False,
        )

        kept_segments: List[Dict[str, Any]] = []
        dropped = 0

        for seg in result.get("segments", []):
            if self._is_silent_segment(seg):
                dropped += 1
                continue

            kept_segments.append({
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": seg["text"].strip(),
                "avg_logprob": seg.get("avg_logprob"),
                "compression_ratio": seg.get("compression_ratio"),
                "no_speech_prob": seg.get("no_speech_prob"),
            })

        # Post-processing repetition removal (repetition_penalty > 1.0)
        kept_segments = self._deduplicate_segments(kept_segments)
        for seg in kept_segments:
            seg["text"] = self._remove_repeated_phrases(seg["text"])

        final_text = " ".join(s["text"] for s in kept_segments).strip()
        final_text = self._remove_repeated_phrases(final_text)

        return {
            "text": final_text,
            "segments": kept_segments,
            "language": result.get("language"),
            "meta": {
                "model": self.model_name,
                "temperature": temperature,
                "segments_total": len(result.get("segments", [])),
                "segments_kept": len(kept_segments),
                "segments_dropped": dropped,
            },
        }
