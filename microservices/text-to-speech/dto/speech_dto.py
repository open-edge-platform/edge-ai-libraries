from typing import Literal

from pydantic import BaseModel, Field

from utils.config_loader import config


MAX_INPUT_LENGTH = 5000


class SpeechRequest(BaseModel):
    model: str = Field(default_factory=lambda: config.models.tts.name)
    input: str = Field(
        min_length=1,
        max_length=MAX_INPUT_LENGTH,
        description="Text to synthesize. Maximum length is 5000 characters.",
    )
    voice: str | None = Field(default=None)
    language: str | None = Field(default=None)
    instructions: str | None = Field(default=None)
    response_format: Literal["wav", "json"] = Field(default="wav")