# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import io
import logging
import os
import wave
from time import perf_counter
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
logger = logging.getLogger("api.routes.voice")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 60
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
TIMEOUT_SECONDS = 120
AUDIO_ANALYZER_URL = os.getenv("AUDIO_ANALYZER_URL", "http://audio-analyzer:8010")
TEXT_TO_SPEECH_URL = os.getenv("TEXT_TO_SPEECH_URL", "http://text-to-speech:8011")
SERVICE_DURATION_HEADER = "X-Voice-Service-Duration-Ms"
METRICS_HEADERS = {
    SERVICE_DURATION_HEADER: {
        "description": (
            "Request-scoped upstream round-trip time in milliseconds, measured by "
            "ViPPET through receipt of the full response body. Includes service queueing "
            "and transport, not just model inference. Excludes browser upload/download."
        ),
        "schema": {"type": "number", "minimum": 0},
    }
}


SpeechVoice = Literal["Ryan", "Miles", "Aaron", "Nora", "Elena", "Kabir", "Angus"]
InferenceDevice = Literal["CPU", "GPU", "NPU"]


class SpeechRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    input: str = Field(min_length=1, max_length=5000)
    voice: SpeechVoice
    device: InferenceDevice | None = None


class TranscriptionResponse(BaseModel):
    text: str = Field(max_length=16000)


def create_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=5.0),
        trust_env=False,
        follow_redirects=False,
    )


async def call_service(
    url: str,
    *,
    files: dict[str, tuple[str, bytes, str]] | None = None,
    data: dict[str, str] | None = None,
    json: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    rejected_detail: str = "The speech service rejected the input.",
) -> httpx.Response:
    started_at = perf_counter()
    try:
        async with (
            asyncio.timeout(TIMEOUT_SECONDS),
            create_client() as client,
            client.stream("POST", url, files=files, data=data, json=json) as upstream,
        ):
            if upstream.status_code in {400, 413, 422}:
                raise HTTPException(400, rejected_detail)
            if upstream.status_code == 429:
                raise HTTPException(503, "The speech service is busy. Try again later.")
            if upstream.status_code != 200:
                logger.warning("Speech service returned HTTP %s", upstream.status_code)
                raise HTTPException(
                    502, "The speech service failed to process the request."
                )
            content = bytearray()
            async for chunk in upstream.aiter_bytes():
                if len(content) + len(chunk) > max_bytes:
                    raise HTTPException(
                        502,
                        "The speech service response exceeded the size limit.",
                    )
                content.extend(chunk)
            result = httpx.Response(
                200, content=bytes(content), headers=upstream.headers
            )
            result.headers[SERVICE_DURATION_HEADER] = (
                f"{(perf_counter() - started_at) * 1000:.3f}"
            )
            return result
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise HTTPException(
            504, "Speech conversion timed out. Try a shorter input."
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, "The speech service is unavailable.") from exc


def validate_audio(content: bytes) -> None:
    try:
        with wave.open(io.BytesIO(content), "rb") as audio:
            frames = audio.getnframes()
            rate = audio.getframerate()
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or not 8000 <= rate <= 48000
                or frames == 0
                or frames > MAX_AUDIO_SECONDS * rate
                or len(audio.readframes(frames)) != frames * 2
            ):
                raise ValueError("Unsupported WAV parameters")
    except (wave.Error, EOFError, ValueError) as exc:
        raise HTTPException(
            400, "Use a valid mono PCM 16-bit WAV, 8-48 kHz, up to 60 seconds."
        ) from exc


@router.post(
    "/transcriptions",
    operation_id="transcribe_voice",
    response_model=TranscriptionResponse,
    responses={200: {"headers": METRICS_HEADERS}},
)
async def transcribe_voice(
    response: Response,
    file: Annotated[
        UploadFile, File(description="Mono PCM 16-bit WAV, up to 60 seconds and 10 MiB")
    ],
    language: Annotated[str, Form(pattern=r"^[a-z]{2}$")] = "en",
    device: Annotated[InferenceDevice | None, Form()] = None,
) -> TranscriptionResponse:
    """Transcribe one independent recording. Previous recordings are never used as context."""
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Audio exceeds the 10 MiB upload limit.")
    validate_audio(content)
    request_data = {
        "language": language,
        "response_format": "json",
        "temperature": "0",
    }
    if device is not None:
        request_data["device"] = device
    upstream = await call_service(
        f"{AUDIO_ANALYZER_URL.rstrip('/')}/v1/audio/transcriptions",
        files={"file": ("recording.wav", content, "audio/wav")},
        data=request_data,
        max_bytes=128 * 1024,
        rejected_detail=(
            "The selected speech-to-text device is unavailable."
            if device is not None
            else "The speech service rejected the input."
        ),
    )
    try:
        result = TranscriptionResponse.model_validate(upstream.json())
        response.headers["Cache-Control"] = "no-store"
        response.headers[SERVICE_DURATION_HEADER] = upstream.headers[
            SERVICE_DURATION_HEADER
        ]
        return result
    except ValueError as exc:
        raise HTTPException(
            502, "The speech service returned an invalid transcription."
        ) from exc


@router.post(
    "/speech",
    operation_id="synthesize_voice",
    response_class=Response,
    responses={
        200: {
            "content": {
                "audio/wav": {"schema": {"type": "string", "format": "binary"}}
            },
            "headers": METRICS_HEADERS,
        }
    },
)
async def synthesize_voice(request: SpeechRequest) -> Response:
    """Synthesize one sentence with the selected voice. Returns WAV audio."""
    request_json = {
        "input": request.input,
        "voice": request.voice,
        "response_format": "wav",
    }
    if request.device is not None:
        request_json["device"] = request.device
    upstream = await call_service(
        f"{TEXT_TO_SPEECH_URL.rstrip('/')}/v1/audio/speech",
        json=request_json,
        rejected_detail=(
            "The selected text-to-speech device is unavailable."
            if request.device is not None
            else "The speech service rejected the input."
        ),
    )
    content = upstream.content
    if (
        upstream.headers.get("content-type", "").split(";")[0] != "audio/wav"
        or len(content) < 44
        or content[:4] != b"RIFF"
        or content[8:12] != b"WAVE"
    ):
        raise HTTPException(502, "The speech service returned invalid audio.")
    return Response(
        content=content,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            SERVICE_DURATION_HEADER: upstream.headers[SERVICE_DURATION_HEADER],
            "Content-Disposition": 'inline; filename="speech.wav"',
            "X-Content-Type-Options": "nosniff",
        },
    )
