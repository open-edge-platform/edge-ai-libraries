import logging
import os

import soundfile as sf

from components.tts_component import TTSComponent
from utils.app_paths import get_session_dir
from utils.config_loader import config
from utils.session_manager import generate_session_id
from utils.storage_manager import StorageManager


logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, session_id=None):
        logger.info("text-to-speech pipeline initialized")
        self.session_id = session_id or generate_session_id()
        self.tts_component = TTSComponent(
            session_id=self.session_id,
            model_name=config.models.tts.name,
            runtime=getattr(config.models.tts, "runtime", "pytorch"),
            device=config.models.tts.device,
            dtype=config.models.tts.dtype,
            model_variant=config.models.tts.model_variant,
            default_speaker=config.models.tts.default_speaker,
            default_language=config.models.tts.default_language,
        )

    def synthesize(
        self,
        text: str,
        language: str | None = None,
        speaker: str | None = None,
        instructions: str | None = None,
        persist_output: bool | None = None,
    ) -> dict:
        result = self.tts_component.synthesize(
            text=text,
            language=language,
            speaker=speaker,
            instructions=instructions,
        )

        output_path = None
        should_persist_output = config.pipeline.persist_outputs if persist_output is None else persist_output
        if should_persist_output:
            session_dir = get_session_dir(self.session_id)
            try:
                os.makedirs(session_dir, exist_ok=True)
                output_path = os.path.join(session_dir, f"speech.{config.audio.output_format}")
                sf.write(output_path, result["audio"], result["sampling_rate"], format=config.audio.output_format.upper())
                StorageManager.save(
                    os.path.join(session_dir, "generation.json"),
                    {
                        "session_id": self.session_id,
                        "model": result["model"],
                        "variant": result["variant"],
                        "speaker": result["speaker"],
                        "language": result["language"],
                        "instructions": result["instructions"],
                        "duration": result["duration"],
                        "text": text,
                        "output_path": output_path,
                    },
                    append=False,
                )
            except Exception as exc:
                logger.exception("Failed to persist synthesized audio for session %s", self.session_id)
                raise RuntimeError("Failed to persist synthesized audio") from exc

        return {
            **result,
            "session_id": self.session_id,
            "output_path": output_path,
        }

    def get_model_info(self) -> dict:
        return self.tts_component.get_model_info()
 