import logging

from components.tts_component import TTSComponent
from utils.config_loader import config


logger = logging.getLogger(__name__)


def _normalize_options(values: list[str] | None) -> set[str]:
    return {value.strip().lower() for value in values or [] if value and value.strip()}


def _validate_default_selection(component: TTSComponent) -> None:
    model_info = component.get_model_info()
    configured_speaker = config.models.tts.default_speaker.strip().lower()
    configured_language = config.models.tts.default_language.strip().lower()

    supported_speakers = _normalize_options(model_info.get("supported_speakers"))
    if supported_speakers and configured_speaker not in supported_speakers:
        raise ValueError(
            f"Configured default_speaker '{config.models.tts.default_speaker}' is not supported by model {config.models.tts.name}."
        )

    supported_languages = _normalize_options(model_info.get("supported_languages"))
    if supported_languages and configured_language not in supported_languages:
        raise ValueError(
            f"Configured default_language '{config.models.tts.default_language}' is not supported by model {config.models.tts.name}."
        )


def preload_models():
    try:
        component = TTSComponent(
            session_id="startup",
            model_name=config.models.tts.name,
            runtime=getattr(config.models.tts, "runtime", "pytorch"),
            device=config.models.tts.device,
            dtype=config.models.tts.dtype,
            model_variant=config.models.tts.model_variant,
            default_speaker=config.models.tts.default_speaker,
            default_language=config.models.tts.default_language,
        )
        _validate_default_selection(component)
        logger.info("Preloaded TTS model %s", config.models.tts.name)
        return component
    except Exception:
        logger.exception("Failed to preload TTS model %s", config.models.tts.name)
        raise
