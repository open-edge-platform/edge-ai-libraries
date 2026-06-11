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


class ASRComponent(PipelineComponent):

    _model = None
    _config = None

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
            from components.asr.diarization.pyannote_diarizer import PyannoteDiarizer

            self.pyannote_diarizer = PyannoteDiarizer(
                hf_token=config.models.asr.hf_token
            )

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
                    speaker_turns = self.pyannote_diarizer.diarize(chunk_path)
                    transcribed_lines = []

                    for sent in transcription["segments"]:
                        text = sent["text"].strip()
                        if not text:
                            continue

                        mid = (sent["start"] + sent["end"]) / 2.0

                        speaker = None
                        for turn in speaker_turns:
                            if turn["start"] <= mid <= turn["end"]:
                                speaker = turn["speaker"]
                                break

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

                        ui_segments.append(segment)
                        self.all_segments.append(segment)
                        transcribed_lines.append(text)

                    transcribed_text = "\n".join(transcribed_lines) + "\n"

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
