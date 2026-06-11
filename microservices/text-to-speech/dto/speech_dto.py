from typing import Literal

from pydantic import BaseModel, Field, field_validator

from utils.config_loader import config


MAX_INPUT_LENGTH = 5000


class SpeechRequest(BaseModel):
    model: str = Field(default_factory=lambda: config.models.tts.name)
    input: str = Field(
        max_length=MAX_INPUT_LENGTH,
        description="Text to synthesize. Maximum length is 5000 characters.",
    )
    voice: str | None = Field(default=None)
    language: str | None = Field(default=None)
    instructions: str | None = Field(default=None)
    response_format: Literal["wav", "json"] = Field(default="wav")

    @field_validator("model", "input", mode="before")
    @classmethod
    def _strip_required_text(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("input")
    @classmethod
    def _validate_input_text(cls, value: str) -> str:
        if not value:
            raise ValueError("Input text is required")
        return value

    @field_validator("voice", "language", "instructions", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    def validate_for_service(self) -> None:
        configured_model_normalized = config.models.tts.name.strip().lower()
        model_variant = config.models.tts.model_variant.strip().lower()

        if "speecht5" in configured_model_normalized or "speech-t5" in configured_model_normalized:
            self._validate_for_speecht5()
            return

        if configured_model_normalized.startswith("qwen/") or "qwen3-tts" in configured_model_normalized:
            self._validate_for_qwen(model_variant)

    def _validate_for_speecht5(self) -> None:
        default_language = config.models.tts.default_language.strip()
        default_speaker = config.models.tts.default_speaker.strip()

        if self.language and self.language.lower() != default_language.lower():
            raise ValueError(f"Only {default_language} is currently supported for speech synthesis.")

        if self.voice and self.voice.lower() != default_speaker.lower():
            raise ValueError(
                f"SpeechT5 currently supports only the configured voice '{default_speaker}'."
            )

        if self.instructions:
            raise ValueError("SpeechT5 does not support free-form voice instructions.")

    def _validate_for_qwen(self, model_variant: str) -> None:
        default_language = config.models.tts.default_language.strip()

        if self.language and self.language.lower() != default_language.lower():
            raise ValueError(f"Only {default_language} is currently supported for speech synthesis.")

        if model_variant == "custom_voice":
            return

        if model_variant == "voice_design":
            if self.voice:
                raise ValueError(
                    "Qwen voice_design does not accept the voice field. Describe the desired voice in instructions instead."
                )
            if not self.instructions:
                raise ValueError(
                    "Qwen voice_design requires instructions describing the desired voice."
                )
            return

        raise ValueError(
            f"Unsupported configured model_variant: {config.models.tts.model_variant}. Use custom_voice or voice_design."
        )