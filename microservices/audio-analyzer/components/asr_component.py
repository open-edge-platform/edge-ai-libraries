import time

from components.base_component import PipelineComponent
import os
from utils.config_loader import config
from utils.latency_store import asr_latency
from utils.storage_manager import StorageManager
from utils.app_paths import get_session_dir
from components.asr.openai.whisper import Whisper as OA_Whisper
from components.asr.openvino.whisper import Whisper as OV_Whisper
from components.asr.openvino_genai.whisper import Whisper as OVGenAIWhisper
from components.asr.whispercpp.whisper import WhisperCpp
import logging
logger = logging.getLogger(__name__)

ENABLE_DIARIZATION = config.models.asr.diarization
DELETE_CHUNK_AFTER_USE = config.pipeline.delete_chunks_after_use

_diar_cfg = getattr(config.models, "diarization", None)
_identity_cfg = getattr(_diar_cfg, "identity", None)
IDENTITY_ENABLED = bool(getattr(_identity_cfg, "enabled", True))
IDENTITY_SIMILARITY_THRESHOLD = float(getattr(_identity_cfg, "similarity_threshold", 0.75))
IDENTITY_LOCK_MIN_DURATION_SEC = float(getattr(_identity_cfg, "lock_min_duration_sec", 0.75))
IDENTITY_SESSION_TTL_SECONDS = float(getattr(_identity_cfg, "session_ttl_seconds", 1800.0))


class ASRComponent(PipelineComponent):

    _model = None
    _config = None
    # Shared across all ASRComponent instances/sessions — keyed by session_id
    # internally — so primary-speaker identity persists across chunk calls
    # for the same session regardless of which ASRComponent instance handles
    # a given chunk.
    _speaker_identity_store = None

    @staticmethod
    def _resolve_backend(provider: str, model_name: str, device: str):
        normalized_provider = provider.lower()
        normalized_model_name = model_name.lower()
        requested_device = str(device)

        if normalized_provider == "whispercpp" and requested_device.upper() != "CPU":
            logger.warning(
                "whispercpp only supports CPU in this service; overriding requested device %s -> CPU",
                requested_device,
            )
            requested_device = "CPU"

        if normalized_provider == "openai" and "whisper" in normalized_model_name:
            return OA_Whisper, (normalized_provider, normalized_model_name, requested_device.lower()), requested_device.lower()

        if normalized_provider == "openvino" and "whisper" in normalized_model_name:
            use_ov_genai = bool(getattr(getattr(config, "app", None), "use_ov_genai", False))
            backend_cls = OVGenAIWhisper if use_ov_genai else OV_Whisper
            return backend_cls, (normalized_provider, normalized_model_name, requested_device.upper(), use_ov_genai), requested_device.upper()

        if normalized_provider == "whispercpp" and "whisper" in normalized_model_name:
            return WhisperCpp, (normalized_provider, normalized_model_name, requested_device.upper()), requested_device.upper()

        raise ValueError(f"Unsupported ASR provider/model: {normalized_provider}/{normalized_model_name}")

    def __init__(self, session_id, provider="openai", model_name="whisper-small", device="CPU", temperature=0.0):

        self.session_id = session_id
        self.temperature = temperature
        self.provider = provider
        self.model_name = model_name
        self.enable_diarization = ENABLE_DIARIZATION
        self.all_segments = []

        backend_cls, model_config_key, resolved_device = self._resolve_backend(provider, model_name, device)

        if ASRComponent._model is None or ASRComponent._config != model_config_key:
            ASRComponent._model = backend_cls(model_name.lower(), resolved_device, None)
            ASRComponent._config = model_config_key

        self.asr = ASRComponent._model

        self.pyannote_diarizer = None
        if self.enable_diarization:
            try:
                from components.asr.diarization.pyannote_diarizer import PyannoteDiarizer
                from utils.ensure_model import _resolve_hf_token

                diar_device = str(
                    getattr(getattr(config.models, "diarization", None), "device", "cpu")
                ).lower()

                self.pyannote_diarizer = PyannoteDiarizer(
                    device=diar_device,
                    hf_token=_resolve_hf_token(),
                )
                logger.info("[DIARIZATION] PyannoteDiarizer loaded on device=%s", diar_device)

                if IDENTITY_ENABLED and ASRComponent._speaker_identity_store is None:
                    from components.asr.diarization.speaker_identity import SpeakerIdentityStore

                    ASRComponent._speaker_identity_store = SpeakerIdentityStore(
                        similarity_threshold=IDENTITY_SIMILARITY_THRESHOLD,
                        lock_min_duration_sec=IDENTITY_LOCK_MIN_DURATION_SEC,
                        session_ttl_seconds=IDENTITY_SESSION_TTL_SECONDS,
                    )
            except Exception as exc:
                logger.warning(
                    "[DIARIZATION] ⚠️  Failed to load PyannoteDiarizer — diarization disabled for this session. "
                    "Cause: %s. "
                    "If this is a 403 error, accept the model at "
                    "https://huggingface.co/pyannote/speaker-diarization-community-1 "
                    "then restart the container.",
                    exc,
                )
                self.enable_diarization = False
                self.pyannote_diarizer = None

    def process(self, input_generator, language: str | None = None):

        project_path = get_session_dir(self.session_id)

        transcript_path = os.path.join(project_path, "transcription.txt")
        StorageManager.save(transcript_path, "", append=False)


        try:

            for chunk_data in input_generator:
                chunk_path = chunk_data["chunk_path"]
                _t0 = time.monotonic()
                transcription = self.asr.transcribe(
                    chunk_path,
                    temperature=self.temperature,
                    language=language,
                )
                asr_latency.record((time.monotonic() - _t0) * 1000)

                ui_segments = []
                transcribed_text = ""

                if self.enable_diarization and transcription.get("segments"):
                    speaker_turns, label_embeddings = self.pyannote_diarizer.diarize(chunk_path)
                    transcribed_lines = []

                    logger.info(
                        "[DIARIZATION] session=%s chunk=%s | pyannote detected %d speaker turn(s): %s",
                        self.session_id,
                        os.path.basename(chunk_path),
                        len(speaker_turns),
                        ", ".join(
                            f"{t['speaker']}[{t['start']:.2f}s–{t['end']:.2f}s]"
                            for t in speaker_turns
                        ) or "none",
                    )
                    logger.info(
                        "[DIARIZATION] session=%s | whisper produced %d segment(s)",
                        self.session_id,
                        len(transcription["segments"]),
                    )

                    primary_map: dict[str, bool] = {}
                    if ASRComponent._speaker_identity_store is not None:
                        primary_map = ASRComponent._speaker_identity_store.resolve(
                            self.session_id, label_embeddings, speaker_turns,
                        )

                    for sent in transcription["segments"]:
                        text = sent["text"].strip()
                        if not text:
                            continue

                        # Assign the speaker turn with the greatest time overlap
                        # (strictly more correct than a midpoint lookup, which
                        # breaks when a segment spans two speaker turns or
                        # falls in a gap between turns).
                        speaker = None
                        best_overlap = 0.0
                        for turn in speaker_turns:
                            overlap = min(sent["end"], turn["end"]) - max(sent["start"], turn["start"])
                            if overlap > best_overlap:
                                best_overlap = overlap
                                speaker = turn["speaker"]

                        is_primary = primary_map.get(speaker, False) if speaker is not None else False
                        logger.info(
                            "[DIARIZATION] segment [%.2fs–%.2fs] max-overlap=%.2fs → speaker=%s is_primary=%s (%s) | text=%r",
                            sent["start"], sent["end"], best_overlap,
                            speaker if speaker else "UNKNOWN",
                            is_primary,
                            "PRIMARY — picked" if is_primary else "SECONDARY — will be dropped downstream",
                            text[:80],
                        )

                        chunk_offset = float(chunk_data.get("start_time", 0.0))
                        start = float(sent["start"]) + chunk_offset
                        end = float(sent["end"]) + chunk_offset

                        segment = {
                            "text": text,
                            "start": start,
                            "end": end
                        }
                        for key in ("avg_logprob", "compression_ratio", "no_speech_prob"):
                            if key in sent:
                                segment[key] = sent[key]
                        if speaker is not None:
                            segment["speaker"] = speaker
                            # Stable, cross-chunk primary-speaker signal — resolved
                            # here in audio-analyzer via speaker embeddings, so
                            # downstream consumers (kiosk-core) don't need their
                            # own model or lock-on logic.
                            segment["is_primary"] = is_primary

                        ui_segments.append(segment)
                        self.all_segments.append(segment)
                        transcribed_lines.append(text)

                    transcribed_text = "\n".join(transcribed_lines) + "\n"

                    primary_count = sum(1 for seg in ui_segments if seg.get("is_primary"))
                    secondary_count = sum(
                        1 for seg in ui_segments if "speaker" in seg and not seg.get("is_primary")
                    )
                    logger.info(
                        "[DIARIZATION] session=%s chunk=%s | speaker resolution summary: "
                        "%d primary segment(s), %d secondary segment(s)",
                        self.session_id,
                        os.path.basename(chunk_path),
                        primary_count,
                        secondary_count,
                    )
                    logger.info(
                        "[DIARIZATION] session=%s chunk=%s | full transcript (all speakers): %r",
                        self.session_id,
                        os.path.basename(chunk_path),
                        transcribed_text.strip()[:200],
                    )

                else:
                    if transcription.get("segments"):
                        transcribed_lines = []
                        for sent in transcription["segments"]:
                            text = sent["text"].strip()
                            if not text:
                                continue

                            start = float(sent["start"]) + float(chunk_data.get("start_time", 0.0))
                            end = float(sent["end"]) + float(chunk_data.get("start_time", 0.0))

                            segment = {
                                "text": text,
                                "start": start,
                                "end": end
                            }
                            for key in ("avg_logprob", "compression_ratio", "no_speech_prob"):
                                if key in sent:
                                    segment[key] = sent[key]

                            ui_segments.append(segment)
                            self.all_segments.append(segment)
                            transcribed_lines.append(text)

                        transcribed_text = "\n".join(transcribed_lines) + "\n"

                yield {
                    **chunk_data,
                    "text": transcribed_text,
                    "segments": ui_segments,
                    "language": transcription.get("language"),
                }

            # ========== FINALIZATION ==========
            if self.all_segments:
                full_updated_lines = []
                full_timestamped_lines = []

                for seg in self.all_segments:
                    text = seg["text"].strip()
                    start = round(seg["start"], 2)
                    end = round(seg["end"], 2)

                    full_updated_lines.append(text)

                    full_timestamped_lines.append(
                        f"[{start} - {end}]: {text}"
                    )

                StorageManager.save(
                    transcript_path,
                    "\n".join(full_updated_lines) + "\n",
                    append=False
                )

                StorageManager.save(
                    os.path.join(project_path, "timestamped_transcription.txt"),
                    "\n".join(full_timestamped_lines) + "\n",
                    append=False
                )

        finally:
            logger.info(f"Transcription Complete: {self.session_id}")
