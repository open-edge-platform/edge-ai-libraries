# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
import re
from time import perf_counter
from typing import Annotated, BinaryIO, Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
logger = logging.getLogger("api.routes.voice")

MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_ERROR_RESPONSE_BYTES = 8 * 1024
TIMEOUT_SECONDS = 20 * 60
AUDIO_ANALYZER_URL = os.getenv("AUDIO_ANALYZER_URL", "http://audio-analyzer:8010")
TEXT_TO_SPEECH_URL = os.getenv("TEXT_TO_SPEECH_URL", "http://text-to-speech:8011")
METRICS_MANAGER_URL = os.getenv("METRICS_MANAGER_URL", "http://metrics-manager:9090")
SERVICE_DURATION_HEADER = "X-Voice-Service-Duration-Ms"
VOICE_METRICS_URL = f"{METRICS_MANAGER_URL.rstrip('/')}/api/v1/metrics"
VOICE_METRICS_TIMEOUT_SECONDS = 2.0
_metrics_tasks: set[asyncio.Task[None]] = set()
MEDIA_TYPE_PATTERN = re.compile(
    r"[A-Za-z0-9!#$%&'*+.^_`|~-]+/[A-Za-z0-9!#$%&'*+.^_`|~-]+"
)
SAFE_AUDIO_VALIDATION_DETAILS = frozenset(
    {
        "No filename provided",
        "Invalid file type",
        "File too large",
        "Uploaded file is empty",
        "Uploaded file is not a valid audio file",
    }
)
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

    input: str = Field(min_length=1, max_length=200)
    voice: SpeechVoice
    device: InferenceDevice | None = None


class TranscriptionResponse(BaseModel):
    text: str = Field(max_length=16000)


def normalize_upload_filename(filename: str | None) -> str:
    basename = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    printable_basename = "".join(
        character for character in basename if character.isprintable()
    )
    return printable_basename[-255:] or "audio"


def normalize_media_type(content_type: str | None) -> str:
    if (
        content_type
        and len(content_type) <= 127
        and MEDIA_TYPE_PATTERN.fullmatch(content_type)
    ):
        return content_type
    return "application/octet-stream"


async def read_safe_error_detail(
    response: httpx.Response, allowed_details: frozenset[str]
) -> str | None:
    content = bytearray()
    async for chunk in response.aiter_bytes():
        if len(content) + len(chunk) > MAX_ERROR_RESPONSE_BYTES:
            return None
        content.extend(chunk)
    try:
        payload = httpx.Response(response.status_code, content=bytes(content)).json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    detail = error.get("message")
    return detail if isinstance(detail, str) and detail in allowed_details else None


def create_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=5.0),
        trust_env=False,
        follow_redirects=False,
    )


async def publish_voice_metric(
    name: Literal["voice_asr", "voice_tts"],
    service_round_trip_ms: float,
    tags: dict[str, str],
) -> None:
    payload = {
        "metrics": [
            {
                "name": name,
                "fields": {"service_round_trip_ms": service_round_trip_ms},
                "tags": tags,
            }
        ]
    }
    try:
        async with httpx.AsyncClient(
            timeout=VOICE_METRICS_TIMEOUT_SECONDS,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = await client.post(VOICE_METRICS_URL, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Unable to publish %s metrics: %s", name, type(exc).__name__)


def schedule_voice_metric(
    name: Literal["voice_asr", "voice_tts"],
    service_round_trip_ms: float,
    tags: dict[str, str],
) -> None:
    task = asyncio.create_task(publish_voice_metric(name, service_round_trip_ms, tags))
    _metrics_tasks.add(task)
    task.add_done_callback(_metrics_tasks.discard)


async def call_service(
    url: str,
    *,
    files: dict[str, tuple[str, BinaryIO, str]] | None = None,
    data: dict[str, str] | None = None,
    json: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    rejected_detail: str = "The speech service rejected the input.",
    safe_rejected_details: frozenset[str] = frozenset(),
) -> httpx.Response:
    started_at = perf_counter()
    try:
        async with (
            asyncio.timeout(TIMEOUT_SECONDS),
            create_client() as client,
            client.stream("POST", url, files=files, data=data, json=json) as upstream,
        ):
            if upstream.status_code in {400, 413, 422}:
                safe_detail = (
                    await read_safe_error_detail(upstream, safe_rejected_details)
                    if safe_rejected_details
                    else None
                )
                raise HTTPException(400, safe_detail or rejected_detail)
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


@router.post(
    "/transcriptions",
    operation_id="transcribe_voice",
    response_model=TranscriptionResponse,
    responses={200: {"headers": METRICS_HEADERS}},
)
async def transcribe_voice(
    response: Response,
    file: Annotated[UploadFile, File(description="Audio file")],
    language: Annotated[str, Form(pattern=r"^[a-z]{2}$")] = "en",
    device: Annotated[InferenceDevice | None, Form()] = None,
) -> TranscriptionResponse:
    """Transcribe one independent recording. Previous recordings are never used as context."""
    request_data = {
        "language": language,
        "response_format": "json",
        "temperature": "0",
    }
    if device is not None:
        request_data["device"] = device
    try:
        upstream = await call_service(
            f"{AUDIO_ANALYZER_URL.rstrip('/')}/v1/audio/transcriptions",
            files={
                "file": (
                    normalize_upload_filename(file.filename),
                    file.file,
                    normalize_media_type(file.content_type),
                )
            },
            data=request_data,
            max_bytes=128 * 1024,
            rejected_detail=(
                "The selected speech-to-text device is unavailable."
                if device is not None
                else "The speech service rejected the input."
            ),
            safe_rejected_details=SAFE_AUDIO_VALIDATION_DETAILS,
        )
    finally:
        await file.close()
    try:
        result = TranscriptionResponse.model_validate(upstream.json())
        service_round_trip_ms = float(upstream.headers[SERVICE_DURATION_HEADER])
        schedule_voice_metric(
            "voice_asr",
            service_round_trip_ms,
            {
                "device": device or "service-default",
                "language": language,
            },
        )
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
    service_round_trip_ms = float(upstream.headers[SERVICE_DURATION_HEADER])
    schedule_voice_metric(
        "voice_tts",
        service_round_trip_ms,
        {
            "device": request.device or "service-default",
            "voice": request.voice,
        },
    )
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
