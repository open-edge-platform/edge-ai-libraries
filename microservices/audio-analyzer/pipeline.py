import logging
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterator

from components.asr_component import ASRComponent
from components.ffmpeg.audio_preprocessing import chunk_by_silence
from utils.config_loader import config
from utils.app_paths import get_session_dir
from utils.storage_manager import StorageManager
from utils.session_manager import generate_session_id

logger = logging.getLogger(__name__)

SENTIMENT_ENABLED = getattr(config, "sentiment", None) and getattr(config.sentiment, "enabled", False)
DELETE_CHUNK_AFTER_USE = getattr(config.pipeline, "delete_chunks_after_use", True)
SESSION_STATE_FILENAME = "session_state.json"

class Pipeline:
    def __init__(self, session_id=None, temperature=None, append_to_session: bool = False):
        logger.info("pipeline initialized")
        self.session_id = session_id or generate_session_id()
        self.append_to_session = append_to_session
        self.temperature = config.models.asr.temperature if temperature is None else temperature
        self.asr_component = ASRComponent(
            self.session_id,
            provider=config.models.asr.provider,
            model_name=config.models.asr.name,
            device=config.models.asr.device,
            temperature=self.temperature,
        )
        self.sentiment_component = None
        if SENTIMENT_ENABLED:
            from components.sentiment_component import SentimentComponent
            self.sentiment_component = SentimentComponent()
        self._session_state = self._load_session_state()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _run_sentiment(self, chunk_path: str) -> dict:
        """Run sentiment on a chunk path; returns empty dict if disabled."""
        if self.sentiment_component and chunk_path:
            return self.sentiment_component.analyze(chunk_path)
        return {}

    def _cleanup_chunk(self, chunk_path: str | None) -> None:
        if DELETE_CHUNK_AFTER_USE and chunk_path and os.path.exists(chunk_path):
            os.remove(chunk_path)

    def _get_session_state_path(self) -> str:
        return os.path.join(get_session_dir(self.session_id), SESSION_STATE_FILENAME)

    def _write_session_state(self, state: dict) -> None:
        state_path = self._get_session_state_path()
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)

    def _load_session_state(self) -> dict:
        if not self.append_to_session:
            return {
                "language": None,
                "duration": 0.0,
                "text": "",
                "segments": [],
                "chunk_sentiments": [],
            }

        state_path = self._get_session_state_path()
        if not os.path.isfile(state_path):
            return {
                "language": None,
                "duration": 0.0,
                "text": "",
                "segments": [],
                "chunk_sentiments": [],
            }

        with open(state_path, encoding="utf-8") as handle:
            data = json.load(handle)

        if isinstance(data, list):
            data = data[-1] if data else {}

        return {
            "language": data.get("language"),
            "duration": float(data.get("duration", 0.0)),
            "text": data.get("text", ""),
            "segments": data.get("segments", []),
            "chunk_sentiments": data.get("chunk_sentiments", []),
        }

    def _offset_segment(self, segment: dict, offset: float) -> dict:
        adjusted = dict(segment)
        adjusted["start"] = float(adjusted.get("start", 0.0)) + offset
        adjusted["end"] = float(adjusted.get("end", 0.0)) + offset
        return adjusted

    def _apply_offset_to_chunk(self, chunk_transcription: dict, offset: float) -> dict:
        adjusted = dict(chunk_transcription)
        adjusted["start_time"] = float(chunk_transcription.get("start_time", 0.0)) + offset
        adjusted["end_time"] = float(chunk_transcription.get("end_time", 0.0)) + offset
        adjusted["segments"] = [self._offset_segment(segment, offset) for segment in chunk_transcription.get("segments", [])]
        return adjusted

    def _persist_session_outputs(
        self,
        language: str | None,
        duration: float,
        text: str,
        segments: list[dict],
        chunk_sentiments: list[dict],
    ) -> None:
        project_path = get_session_dir(self.session_id)
        transcript_path = os.path.join(project_path, "transcription.txt")
        timestamped_path = os.path.join(project_path, "timestamped_transcription.txt")

        StorageManager.save(transcript_path, f"{text.strip()}\n" if text else "", append=False)

        timestamped_lines = [
            f"[{round(float(segment.get('start', 0.0)), 2)} - {round(float(segment.get('end', 0.0)), 2)}]: {segment.get('text', '').strip()}"
            for segment in segments
            if segment.get("text", "").strip()
        ]
        StorageManager.save(timestamped_path, "\n".join(timestamped_lines) + ("\n" if timestamped_lines else ""), append=False)
        self._write_session_state({
            "language": language,
            "duration": round(duration, 3),
            "text": text,
            "segments": segments,
            "chunk_sentiments": chunk_sentiments,
        })

    def _iter_chunk_transcriptions(self, input, language: str | None = None):
        """Yield (chunk_transcription, sentiment_result) for each chunk.
        ASR and sentiment run in parallel via a thread pool."""
        chunk_generator = chunk_by_silence(input, self.session_id)

        if not SENTIMENT_ENABLED:
            for chunk in self.asr_component.process(chunk_generator, language=language):
                self._cleanup_chunk(chunk.get("chunk_path"))
                yield chunk, {}
            return

        # Buffer chunks so we can fan-out ASR + sentiment concurrently
        with ThreadPoolExecutor(max_workers=2) as pool:
            for chunk_transcription in self.asr_component.process(chunk_generator, language=language):
                chunk_path = chunk_transcription.get("chunk_path")
                fut = pool.submit(self._run_sentiment, chunk_path)
                sentiment = fut.result()
                self._cleanup_chunk(chunk_path)
                yield chunk_transcription, sentiment

    def _build_verbose_segment(self, segment_id: int, segment: dict, include_speaker: bool = False) -> dict:
        verbose_segment = {
            "id": segment_id,
            "seek": 0,
            "start": float(segment.get("start", 0.0)),
            "end": float(segment.get("end", 0.0)),
            "text": segment.get("text", "").strip(),
            "tokens": [],
            "temperature": self.temperature,
            "avg_logprob": segment.get("avg_logprob"),
            "compression_ratio": segment.get("compression_ratio"),
            "no_speech_prob": segment.get("no_speech_prob"),
        }
        if include_speaker and "speaker" in segment:
            verbose_segment["speaker"] = segment["speaker"]
        return verbose_segment

    def _resolve_output_language(
        self,
        current_language: str | None,
        chunk_transcription: dict,
    ) -> str | None:
        return current_language or chunk_transcription.get("language")

    def stream_transcribe(self, input, language: str | None = None):
        detected_language = language or self._session_state.get("language")
        base_duration = float(self._session_state.get("duration", 0.0))
        all_segments = [dict(segment) for segment in self._session_state.get("segments", [])]
        text_parts = [self._session_state["text"]] if self._session_state.get("text") else []
        duration = base_duration
        chunk_sentiments = list(self._session_state.get("chunk_sentiments", []))
        chunk_index_offset = len(chunk_sentiments)

        for chunk_index, (chunk_transcription, sentiment) in enumerate(
            self._iter_chunk_transcriptions(input, language=language)
        ):
            chunk_transcription = self._apply_offset_to_chunk(chunk_transcription, base_duration)
            detected_language = self._resolve_output_language(detected_language, chunk_transcription)
            chunk_text = chunk_transcription.get("text", "").strip()
            if chunk_text:
                text_parts.append(chunk_text)
            if sentiment:
                chunk_sentiments.append(sentiment)

            verbose_segments = []
            for segment in chunk_transcription.get("segments", []):
                all_segments.append(segment)
                duration = max(duration, float(segment.get("end", 0.0)))
                verbose_segments.append(
                    self._build_verbose_segment(len(all_segments) - 1, segment, include_speaker=True)
                )

            duration = max(duration, float(chunk_transcription.get("end_time", 0.0)))

            chunk_event = {
                "event": "transcription.chunk",
                "chunk_index": chunk_index_offset + chunk_index,
                "language": detected_language,
                "start_time": float(chunk_transcription.get("start_time", 0.0)),
                "end_time": float(chunk_transcription.get("end_time", 0.0)),
                "text": chunk_text,
                "segments": verbose_segments,
                "is_final": False,
            }
            if sentiment:
                chunk_event["sentiment"] = sentiment
            yield chunk_event

        final_text = "\n".join(part for part in text_parts if part).strip()

        final_event = {
            "event": "transcription.completed",
            "language": detected_language,
            "duration": round(duration, 3),
            "text": final_text,
            "segments": [
                self._build_verbose_segment(index, segment, include_speaker=True)
                for index, segment in enumerate(all_segments)
            ],
            "is_final": True,
        }
        if chunk_sentiments:
            from components.sentiment_component import SentimentComponent
            final_event["sentiment_summary"] = SentimentComponent.aggregate(
                chunk_sentiments,
                recency_weight=getattr(config.sentiment, "recency_weight", 0.7),
                peak_label=getattr(config.sentiment, "peak_label", "angry"),
            )
        self._persist_session_outputs(detected_language, duration, final_text, all_segments, chunk_sentiments)
        yield final_event

    def transcribe(self, input, language: str | None = None) -> dict:
        detected_language = language or self._session_state.get("language")
        base_duration = float(self._session_state.get("duration", 0.0))
        segments = [dict(segment) for segment in self._session_state.get("segments", [])]
        text_parts = [self._session_state["text"]] if self._session_state.get("text") else []
        duration = base_duration
        chunk_sentiments = list(self._session_state.get("chunk_sentiments", []))

        for chunk_transcription, sentiment in self._iter_chunk_transcriptions(input, language=language):
            chunk_transcription = self._apply_offset_to_chunk(chunk_transcription, base_duration)
            detected_language = self._resolve_output_language(detected_language, chunk_transcription)
            chunk_text = chunk_transcription.get("text", "").strip()
            if chunk_text:
                text_parts.append(chunk_text)
            if sentiment:
                chunk_sentiments.append(sentiment)

            for segment in chunk_transcription.get("segments", []):
                segments.append(segment)
                duration = max(duration, float(segment.get("end", 0.0)))

            duration = max(duration, float(chunk_transcription.get("end_time", 0.0)))

        full_text = "\n".join(part for part in text_parts if part).strip()

        verbose_segments = []
        for index, segment in enumerate(segments):
            verbose_segments.append(self._build_verbose_segment(index, segment, include_speaker=False))

        result = {
            "task": "transcribe",
            "language": detected_language,
            "duration": round(duration, 3),
            "text": full_text,
            "segments": verbose_segments,
        }

        if chunk_sentiments:
            from components.sentiment_component import SentimentComponent
            result["sentiment_summary"] = SentimentComponent.aggregate(
                chunk_sentiments,
                recency_weight=getattr(config.sentiment, "recency_weight", 0.7),
                peak_label=getattr(config.sentiment, "peak_label", "angry"),
            )

        self._persist_session_outputs(detected_language, duration, full_text, segments, chunk_sentiments)

        return result