import math
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from dto.audiosource import AudioSource


SUPPORTED_OPENAI_MODELS = {"whisper-1"}
SUPPORTED_RESPONSE_FORMATS = {"json", "text", "verbose_json", "srt", "vtt"}
MAX_LANGUAGE_LENGTH = 32
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 1.0
 
class TranscriptionRequest(BaseModel):
    audio_filename: str
    source_type: Optional[AudioSource] = AudioSource.AUDIO_FILE


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def validate_transcription_options(
    *,
    temperature: float,
    language: str | None = None,
    prompt: str | None = None,
    model: str | None = None,
    response_format: str | None = None,
) -> tuple[str | None, str | None]:
    if model is not None and model not in SUPPORTED_OPENAI_MODELS:
        raise HTTPException(status_code=400, detail=f"Unsupported model: {model}")

    if response_format is not None and response_format not in SUPPORTED_RESPONSE_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported response_format: {response_format}")

    if not math.isfinite(temperature) or not (MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE):
        raise HTTPException(
            status_code=400,
            detail=f"temperature must be between {MIN_TEMPERATURE} and {MAX_TEMPERATURE}",
        )

    normalized_language = _normalize_optional_text(language)
    if normalized_language and len(normalized_language) > MAX_LANGUAGE_LENGTH:
        raise HTTPException(status_code=400, detail="language is too long")

    normalized_prompt = _normalize_optional_text(prompt)
    if normalized_prompt:
        raise HTTPException(status_code=400, detail="prompt is not currently supported")

    return normalized_language, normalized_prompt