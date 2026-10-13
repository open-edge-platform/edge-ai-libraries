# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
import re
from time import perf_counter
from typing import Annotated, BinaryIO, Literal, cast

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from audio_assets import AudioAssetsManager
from api.dependencies.audio_jobs import (
    configure_audio_pipeline_job_manager_factory,
    get_audio_pipeline_job_manager,
)
from managers.audio_pipeline_job_manager import (
    AudioPipelineJobManager,
    AudioPipelineJobStatus,
)
from managers.audio_pipeline_manager import get_audio_pipeline_manager

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


class AudioPipelineDefaultsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audio: str | None = None
    language: str | None = None
    text: str | None = None
    voice: str | None = None


class AudioPipelineVariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    device: Literal["CPU", "GPU", "NPU"]


class AudioPipelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    type: Literal["audio"]
    operation: Literal["speech_to_text", "text_to_speech"]
    tags: list[str]
    thumbnail: str | None = None
    required_models: list[str]
    variants: list[AudioPipelineVariantResponse]
    defaults: AudioPipelineDefaultsResponse
    available: bool
    unavailable_reason: str | None = None


class AudioPipelineJobStartResponse(BaseModel):
    job_id: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]


class AudioPipelineRunRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    input: str = Field(min_length=1, max_length=200)
    voice: SpeechVoice


class AudioPipelineJobResponse(BaseModel):
    id: str
    pipeline_id: str
    pipeline_name: str
    variant_id: str
    variant_name: str
    device: Literal["CPU", "GPU", "NPU"]
    operation: Literal["speech_to_text", "text_to_speech"]
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    created_at: str
    modified_at: str
    transcript: str | None = None
    artifact_url: str | None = None
    service_round_trip_ms: float | None = None
    error: str | None = None


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


async def execute_transcription(
    file: BinaryIO,
    filename: str,
    content_type: str,
    language: str,
    device: str | None,
) -> tuple[str, float]:
    request_data = {
        "language": language,
        "response_format": "json",
        "temperature": "0",
    }
    if device is not None:
        request_data["device"] = device
    upstream = await call_service(
        f"{AUDIO_ANALYZER_URL.rstrip('/')}/v1/audio/transcriptions",
        files={
            "file": (
                normalize_upload_filename(filename),
                file,
                normalize_media_type(content_type),
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
    try:
        result = TranscriptionResponse.model_validate(upstream.json())
        service_round_trip_ms = float(upstream.headers[SERVICE_DURATION_HEADER])
    except ValueError as exc:
        raise HTTPException(
            502, "The speech service returned an invalid transcription."
        ) from exc
    schedule_voice_metric(
        "voice_asr",
        service_round_trip_ms,
        {
            "device": device or "service-default",
            "language": language,
        },
    )
    return result.text, service_round_trip_ms


async def execute_synthesis(
    text: str,
    voice: str,
    device: str | None,
) -> tuple[bytes, float]:
    request_json = {
        "input": text,
        "voice": voice,
        "response_format": "wav",
    }
    if device is not None:
        request_json["device"] = device
    upstream = await call_service(
        f"{TEXT_TO_SPEECH_URL.rstrip('/')}/v1/audio/speech",
        json=request_json,
        rejected_detail=(
            "The selected text-to-speech device is unavailable."
            if device is not None
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
            "device": device or "service-default",
            "voice": voice,
        },
    )
    return content, service_round_trip_ms


def _create_audio_pipeline_job_manager() -> AudioPipelineJobManager:
    return AudioPipelineJobManager(
        get_audio_pipeline_manager(),
        AudioAssetsManager(),
        execute_transcription,
        execute_synthesis,
    )


configure_audio_pipeline_job_manager_factory(_create_audio_pipeline_job_manager)

AudioJobManagerDependency = Annotated[
    AudioPipelineJobManager,
    Depends(get_audio_pipeline_job_manager),
]


def audio_job_response(job) -> AudioPipelineJobResponse:
    return AudioPipelineJobResponse(
        id=job.id,
        pipeline_id=job.pipeline_id,
        pipeline_name=job.pipeline_name,
        variant_id=job.variant_id,
        variant_name=job.variant_name,
        device=job.device,
        operation=job.operation,
        status=job.status,
        created_at=job.created_at.isoformat(),
        modified_at=job.modified_at.isoformat(),
        transcript=job.transcript,
        artifact_url=(
            f"/api/v1/voice/jobs/{job.id}/artifact"
            if job.artifact_path is not None
            else None
        ),
        service_round_trip_ms=job.service_round_trip_ms,
        error=job.error,
    )


@router.get("/pipelines", response_model=list[AudioPipelineResponse])
async def list_audio_pipelines() -> list[AudioPipelineResponse]:
    return [
        AudioPipelineResponse.model_validate(pipeline)
        for pipeline in get_audio_pipeline_manager().list_pipelines()
    ]


@router.post(
    "/pipelines/{pipeline_id}/runs",
    response_model=AudioPipelineJobStartResponse,
    status_code=202,
)
async def run_audio_pipeline(
    pipeline_id: str,
    manager: AudioJobManagerDependency,
    request: AudioPipelineRunRequest | None = None,
) -> AudioPipelineJobStartResponse:
    return await _start_audio_pipeline_job(manager, pipeline_id, None, request)


@router.post(
    "/pipelines/{pipeline_id}/variants/{variant_id}/runs",
    response_model=AudioPipelineJobStartResponse,
    status_code=202,
)
async def run_audio_pipeline_variant(
    pipeline_id: str,
    variant_id: str,
    manager: AudioJobManagerDependency,
    request: AudioPipelineRunRequest | None = None,
) -> AudioPipelineJobStartResponse:
    return await _start_audio_pipeline_job(manager, pipeline_id, variant_id, request)


async def _start_audio_pipeline_job(
    manager: AudioPipelineJobManager,
    pipeline_id: str,
    variant_id: str | None,
    request: AudioPipelineRunRequest | None,
) -> AudioPipelineJobStartResponse:
    try:
        if request is None:
            job = await manager.start_job(pipeline_id, variant_id)
        else:
            job = await manager.start_job(
                pipeline_id,
                variant_id,
                input_text=request.input,
                voice=request.voice,
            )
    except ValueError as exc:
        message = str(exc)
        if "variant" in message and "not found" in message:
            raise HTTPException(404, "Audio pipeline variant not found.") from exc
        if "not found" in message:
            raise HTTPException(404, "Audio pipeline not found.") from exc
        if "do not accept TTS overrides" in message:
            raise HTTPException(
                400, "This Audio pipeline does not accept TTS input."
            ) from exc
        raise HTTPException(409, "Audio pipeline is unavailable.") from exc
    return AudioPipelineJobStartResponse(
        job_id=job.id,
        status=cast(
            Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"],
            job.status.value,
        ),
    )


@router.get("/jobs/{job_id}", response_model=AudioPipelineJobResponse)
async def get_audio_pipeline_job(
    job_id: str,
    manager: AudioJobManagerDependency,
) -> AudioPipelineJobResponse:
    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Audio pipeline job not found.")
    return audio_job_response(job)


@router.get("/jobs/{job_id}/artifact", response_class=FileResponse)
async def get_audio_pipeline_artifact(
    job_id: str,
    manager: AudioJobManagerDependency,
) -> FileResponse:
    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Audio pipeline job not found.")
    if (
        job.status not in {AudioPipelineJobStatus.COMPLETED, "COMPLETED"}
        or job.artifact_path is None
        or not os.path.isfile(job.artifact_path)
    ):
        raise HTTPException(409, "Audio pipeline artifact is not available.")
    return FileResponse(
        job.artifact_path,
        media_type="audio/wav",
        filename="speech.wav",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


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
    try:
        text, service_round_trip_ms = await execute_transcription(
            file.file,
            file.filename or "audio",
            file.content_type or "application/octet-stream",
            language,
            device,
        )
    finally:
        await file.close()
    response.headers["Cache-Control"] = "no-store"
    response.headers[SERVICE_DURATION_HEADER] = f"{service_round_trip_ms:.3f}"
    return TranscriptionResponse(text=text)


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
    content, service_round_trip_ms = await execute_synthesis(
        request.input,
        request.voice,
        request.device,
    )
    return Response(
        content=content,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            SERVICE_DURATION_HEADER: f"{service_round_trip_ms:.3f}",
            "Content-Disposition": 'inline; filename="speech.wav"',
            "X-Content-Type-Options": "nosniff",
        },
    )
