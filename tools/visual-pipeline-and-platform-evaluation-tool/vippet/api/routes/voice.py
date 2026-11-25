# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import io
import logging
import os
import re
import wave
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from audio_assets import SAMPLE_AUDIO_RECORDINGS, AudioAssetsManager
from audio_service_client import (
    SAMPLE_AUDIO_TIMEOUT_SECONDS,
    create_sample_audio_client,
    normalize_media_type,
    normalize_upload_filename,
)
from audio_errors import (
    AudioInputTooLargeError,
    AudioPipelineError,
    AudioPipelineNotFoundError,
    AudioPipelineVariantNotFoundError,
    AudioRecordingInputNotAcceptedError,
    AudioRecordingNotFoundError,
    AudioSTTInputNotAcceptedError,
    AudioTTSInputNotAcceptedError,
)
from api import api_schemas as schemas
from api.dependencies.audio_jobs import (
    get_audio_pipeline_job_manager,
    require_voice_available,
)
from internal_types import (
    InternalAudioJobState,
    InternalAudioPipelineRecordingInput,
    InternalAudioPipelineSTTInput,
)
from managers.audio_pipeline_job_manager import AudioPipelineJobManager
from managers.audio_pipeline_manager import get_audio_pipeline_manager

router = APIRouter(dependencies=[Depends(require_voice_available)])

logger = logging.getLogger("api.routes.voice")
MAX_SAMPLE_AUDIO_BYTES = 2 * 1024 * 1024

_AUDIO_PIPELINE_RUN_REQUEST_SCHEMA = schemas.AudioPipelineRunRequest.model_json_schema()
# Inline the voice enum because openapi_extra embeds this schema without its own
# document root, leaving Pydantic's #/$defs/SpeechVoice reference unresolved.
_AUDIO_PIPELINE_RUN_REQUEST_SCHEMA["properties"]["voice"] = (
    _AUDIO_PIPELINE_RUN_REQUEST_SCHEMA.pop("$defs")["SpeechVoice"]
)


AUDIO_PIPELINE_RUN_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "oneOf": [
                        _AUDIO_PIPELINE_RUN_REQUEST_SCHEMA,
                        schemas.AudioRecordingRunRequest.model_json_schema(),
                    ]
                }
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file", "language"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "language": {
                            "type": "string",
                            "pattern": "^[a-z]{2}$",
                        },
                    },
                }
            },
        },
    }
}


AudioJobManagerDependency = Annotated[
    AudioPipelineJobManager,
    Depends(get_audio_pipeline_job_manager),
]


@router.get("/pipelines", response_model=list[schemas.AudioPipelineResponse])
async def list_audio_pipelines() -> list[schemas.AudioPipelineResponse]:
    """
    # List Audio Pipelines

    ## Operation
    Return the read-only audio catalog, including variants and default inputs.

    ## Response Codes
    | Code | Description |
    |------|-------------|
    | 200 | Audio pipeline definitions |
    | 503 | Voice initialization failed |
    """
    return [
        schemas.AudioPipelineResponse.model_validate(pipeline)
        for pipeline in get_audio_pipeline_manager().list_pipelines()
    ]


@router.get("/recordings", response_model=list[schemas.AudioRecordingResponse])
async def list_audio_recordings() -> list[schemas.AudioRecordingResponse]:
    """
    # List Audio Recordings

    ## Operation
    Return bundled recordings with their durations and public playback URLs.

    ## Response Codes
    | Code | Description |
    |------|-------------|
    | 200 | Available audio recordings |
    | 503 | Voice initialization failed |
    """
    return [
        schemas.AudioRecordingResponse(
            filename=asset.filename,
            duration_seconds=asset.duration_seconds,
            audio_url=f"/api/v1/voice/recordings/{quote(asset.filename)}/audio",
        )
        for asset in AudioAssetsManager().list_assets()
    ]


@router.get("/recordings/{filename}/audio", response_class=FileResponse)
async def get_audio_recording(filename: str) -> FileResponse:
    """
    # Get Audio Recording

    ## Parameters
    - `filename`: Name of a registered recording, not an arbitrary file path.

    ## Response Codes
    | Code | Description |
    |------|-------------|
    | 200 | WAV recording with caching disabled |
    | 404 | Recording does not exist |
    | 503 | Voice initialization failed |
    """
    asset = AudioAssetsManager().get_asset(filename)
    if asset is None or not os.path.isfile(asset.path):
        raise HTTPException(404, "Audio recording not found.")
    return FileResponse(
        asset.path,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def _get_sample_audio_recording(filename: str) -> dict[str, str]:
    recording = next(
        (item for item in SAMPLE_AUDIO_RECORDINGS if item["filename"] == filename),
        None,
    )
    if recording is None:
        raise HTTPException(404, "Sample audio recording not found.")
    return recording


async def _fetch_sample_audio(recording: dict[str, str]) -> bytes:
    try:
        async with asyncio.timeout(SAMPLE_AUDIO_TIMEOUT_SECONDS):
            async with create_sample_audio_client() as client:
                async with client.stream("GET", recording["url"]) as upstream:
                    if upstream.status_code != 200:
                        raise HTTPException(502, "Unable to download audio sample.")
                    content_type = upstream.headers.get("content-type", "")
                    content_type = content_type.split(";", maxsplit=1)[0].lower()
                    if content_type not in {"audio/wav", "audio/x-wav"}:
                        raise HTTPException(502, "Invalid audio sample response.")
                    content_length = upstream.headers.get("content-length")
                    if content_length is not None:
                        try:
                            if int(content_length) > MAX_SAMPLE_AUDIO_BYTES:
                                raise HTTPException(
                                    502, "Audio sample exceeds the size limit."
                                )
                        except ValueError as exc:
                            raise HTTPException(
                                502, "Invalid audio sample response."
                            ) from exc

                    audio_bytes = bytearray()
                    async for chunk in upstream.aiter_bytes():
                        if len(audio_bytes) + len(chunk) > MAX_SAMPLE_AUDIO_BYTES:
                            raise HTTPException(
                                502, "Audio sample exceeds the size limit."
                            )
                        audio_bytes.extend(chunk)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise HTTPException(504, "Audio sample download timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Unable to download audio sample.") from exc

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as audio:
            is_valid_wav = (
                audio.getnchannels() > 0
                and audio.getframerate() > 0
                and audio.getnframes() > 0
            )
    except (EOFError, OSError, wave.Error) as exc:
        raise HTTPException(502, "Invalid audio sample response.") from exc
    if not is_valid_wav:
        raise HTTPException(502, "Invalid audio sample response.")
    return bytes(audio_bytes)


def _sample_audio_recording_response(
    recording: dict[str, str], downloaded: bool
) -> schemas.SampleAudioRecordingResponse:
    return schemas.SampleAudioRecordingResponse(
        filename=recording["filename"],
        gender=recording["gender"],  # type: ignore[arg-type]
        format=recording["format"],
        sample_rate=recording["sample_rate"],
        description=recording["description"],
        downloaded=downloaded,
    )


@router.get(
    "/sample-recordings",
    response_model=list[schemas.SampleAudioRecordingResponse],
)
async def list_sample_audio_recordings() -> list[schemas.SampleAudioRecordingResponse]:
    """
    # List Sample Audio Recordings

    ## Operation
    Return the allowlisted sample catalog, including audio metadata and whether
    each recording is already available locally. No files are downloaded.

    ## Response Codes
    | Code | Description |
    |------|-------------|
    | 200 | Sample recordings and their local download status |
    | 503 | Voice initialization failed |
    """
    assets = AudioAssetsManager()
    return [
        _sample_audio_recording_response(
            recording, assets.get_asset(recording["filename"]) is not None
        )
        for recording in SAMPLE_AUDIO_RECORDINGS
    ]


@router.post(
    "/sample-recordings/{filename}/download",
    response_model=schemas.SampleAudioRecordingResponse,
    responses={
        404: {"description": "The filename is not in the sample catalog."},
        502: {"description": "The upstream sample could not be downloaded."},
        504: {"description": "The upstream sample download timed out."},
    },
)
async def download_sample_audio_recording(
    filename: str,
) -> schemas.SampleAudioRecordingResponse:
    """
    # Download Sample Audio Recording

    ## Operation
    Download an allowlisted WAV sample and store it locally for playback and
    speech-to-text pipelines. Reuse an existing valid local recording.

    ## Parameters
    - `filename`: Sample filename from the catalog, not a URL or arbitrary path.

    ## Response Codes
    | Code | Description |
    |------|-------------|
    | 200 | Sample is available locally |
    | 404 | Filename is not in the sample catalog |
    | 500 | Sample could not be stored locally |
    | 502 | Upstream download failed or returned invalid or oversized audio |
    | 503 | Voice initialization failed |
    | 504 | Upstream download timed out |
    """
    recording = _get_sample_audio_recording(filename)
    assets = AudioAssetsManager()
    if assets.get_asset(filename) is None:
        audio_bytes = await _fetch_sample_audio(recording)
        try:
            await asyncio.to_thread(assets.save_sample_recording, filename, audio_bytes)
        except (OSError, ValueError) as exc:
            logger.error(
                "Unable to store sample audio recording: %s", type(exc).__name__
            )
            raise HTTPException(500, "Unable to store audio sample.") from exc
    return _sample_audio_recording_response(recording, True)


@router.post(
    "/pipelines/{pipeline_id}/variants/{variant_id}/runs",
    response_model=schemas.AudioPipelineJobStartResponse,
    status_code=202,
    openapi_extra=AUDIO_PIPELINE_RUN_OPENAPI,
)
async def run_audio_pipeline_variant(
    pipeline_id: str,
    variant_id: str,
    request: Request,
    manager: AudioJobManagerDependency,
) -> schemas.AudioPipelineJobStartResponse:
    """
    # Run Audio Pipeline Variant

    ## Operation
    Start an asynchronous speech-to-text or text-to-speech job on the selected
    variant. Poll its status through the audio job endpoints.

    ## Request Body
    - JSON: `input` and `voice` for synthesis, or `recording` and `language`
      for transcription of a registered recording.
    - Multipart: `file` and a two-letter `language` for uploaded audio.

    ## Response Codes
    | Code | Description |
    |------|-------------|
    | 202 | Job ID and initial state |
    | 400 | Pipeline does not accept the selected input type |
    | 404 | Pipeline, variant, or recording does not exist |
    | 409 | Pipeline cannot run with the supplied inputs |
    | 413 | Audio upload exceeds the size limit |
    | 415 | Unsupported request content type |
    | 422 | Invalid request fields |
    | 503 | Voice initialization failed |
    """
    return await _start_audio_pipeline_request(
        request,
        manager,
        pipeline_id,
        variant_id,
    )


async def _start_audio_pipeline_request(
    request: Request,
    manager: AudioPipelineJobManager,
    pipeline_id: str,
    variant_id: str,
) -> schemas.AudioPipelineJobStartResponse:
    media_type = request.headers.get("content-type", "").partition(";")[0].lower()
    if media_type == "application/json":
        body = await request.body()
        try:
            tts_request = schemas.AudioPipelineRunRequest.model_validate_json(body)
        except ValidationError:
            try:
                recording_request = (
                    schemas.AudioRecordingRunRequest.model_validate_json(body)
                )
            except ValidationError as exc:
                raise HTTPException(422, "Invalid Audio pipeline run request.") from exc
            return await _start_audio_pipeline_job(
                manager,
                pipeline_id,
                variant_id,
                recording_request=recording_request,
            )
        return await _start_audio_pipeline_job(
            manager,
            pipeline_id,
            variant_id,
            tts_request=tts_request,
        )

    if media_type == "multipart/form-data":
        async with request.form(max_files=1, max_fields=2) as form:
            upload = form.get("file")
            language = form.get("language")
            if not isinstance(upload, StarletteUploadFile) or not isinstance(
                language, str
            ):
                raise HTTPException(422, "Invalid managed STT input.")
            if re.fullmatch(r"[a-z]{2}", language) is None:
                raise HTTPException(422, "Invalid managed STT language.")
            return await _start_audio_pipeline_job(
                manager,
                pipeline_id,
                variant_id,
                stt_input=InternalAudioPipelineSTTInput(
                    file=upload.file,
                    filename=normalize_upload_filename(upload.filename),
                    content_type=normalize_media_type(upload.content_type),
                    language=language,
                ),
            )

    raise HTTPException(415, "Unsupported Audio pipeline request type.")


async def _start_audio_pipeline_job(
    manager: AudioPipelineJobManager,
    pipeline_id: str,
    variant_id: str,
    *,
    tts_request: schemas.AudioPipelineRunRequest | None = None,
    stt_input: InternalAudioPipelineSTTInput | None = None,
    recording_request: schemas.AudioRecordingRunRequest | None = None,
) -> schemas.AudioPipelineJobStartResponse:
    try:
        if recording_request is not None:
            job = await manager.start_job(
                pipeline_id,
                variant_id,
                recording_input=InternalAudioPipelineRecordingInput(
                    filename=recording_request.recording,
                    language=recording_request.language,
                ),
            )
        elif stt_input is not None:
            job = await manager.start_job(
                pipeline_id,
                variant_id,
                stt_input=stt_input,
            )
        elif tts_request is not None:
            job = await manager.start_job(
                pipeline_id,
                variant_id,
                input_text=tts_request.input,
                voice=tts_request.voice.value,
            )
        else:
            raise HTTPException(422, "Invalid Audio pipeline run request.")
    except AudioInputTooLargeError as exc:
        raise HTTPException(413, "The input exceeds the upload limit.") from exc
    except AudioRecordingNotFoundError as exc:
        raise HTTPException(404, "Audio recording not found.") from exc
    except AudioPipelineVariantNotFoundError as exc:
        raise HTTPException(404, "Audio pipeline variant not found.") from exc
    except AudioPipelineNotFoundError as exc:
        raise HTTPException(404, "Audio pipeline not found.") from exc
    except AudioRecordingInputNotAcceptedError as exc:
        raise HTTPException(
            400, "This Audio pipeline does not accept recording input."
        ) from exc
    except AudioTTSInputNotAcceptedError as exc:
        raise HTTPException(
            400, "This Audio pipeline does not accept TTS input."
        ) from exc
    except AudioSTTInputNotAcceptedError as exc:
        raise HTTPException(
            400, "This Audio pipeline does not accept STT input."
        ) from exc
    except AudioPipelineError as exc:
        raise HTTPException(409, "Audio pipeline is unavailable.") from exc
    return schemas.AudioPipelineJobStartResponse(
        job_id=job.id,
        status=schemas.AudioJobState(job.status.value),
    )


@router.get("/jobs/{job_id}/artifact", response_class=FileResponse)
async def get_audio_pipeline_artifact(
    job_id: str,
    manager: AudioJobManagerDependency,
) -> FileResponse:
    """
    # Get Audio Pipeline Artifact

    ## Parameters
    - `job_id`: ID of a completed text-to-speech job.

    ## Response Codes
    | Code | Description |
    |------|-------------|
    | 200 | Generated WAV audio with caching disabled |
    | 404 | Job does not exist |
    | 409 | Job has no available audio artifact |
    | 503 | Voice initialization failed |
    """
    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Audio pipeline job not found.")
    if (
        job.status != InternalAudioJobState.COMPLETED
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
