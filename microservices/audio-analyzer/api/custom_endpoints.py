import json
import logging
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from dto.audiosource import AudioSource
from dto.transcription_dto import validate_transcription_options
from dto.vss_dto import (
    AvailableModelsResponse,
    TranscriptionStatus,
    VssTranscriptionForm,
    VssTranscriptionResponse,
    WhisperModelInfo,
)
from pipeline import Pipeline
from utils.app_paths import get_session_dir
from utils.audio_util import save_audio_file
from utils.config_loader import config
from utils.latency_store import asr_latency
from utils.minio_handler import MinioHandler
from utils.session_manager import generate_session_id, resolve_requested_session_id

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health():
    return JSONResponse(content={"status": "ok"}, status_code=200)


@router.get("/v1/model-info")
def asr_model_info():
    return JSONResponse(content={
        "model": config.models.asr.name,
        "provider": config.models.asr.provider,
        "device": config.models.asr.device,
        "weight_format": getattr(config.models.asr, "weight_format", None),
    })


@router.get("/v1/performance")
def asr_performance():
    return JSONResponse(content={"latency": asr_latency.stats()})


@router.post("/v1/audio/transcriptions/stream")
def stream_transcribe_audio(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    language: str | None = Form("en"),
    temperature: float = Form(0.0),
):
    language, _ = validate_transcription_options(
        temperature=temperature,
        language=language,
    )

    try:
        session_id, continue_session = resolve_requested_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _, filepath = save_audio_file(file, session_id=session_id)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=400, detail=f"Audio file not found: {filepath}")

    pipeline = Pipeline(session_id=session_id, temperature=temperature, append_to_session=continue_session)

    def iter_stream():
        request = SimpleNamespace(
            audio_filename=filepath,
            source_type=AudioSource.AUDIO_FILE,
        )
        for chunk in pipeline.stream_transcribe(request, language=language):
            yield json.dumps(chunk) + "\n"

    response = StreamingResponse(iter_stream(), media_type="application/x-ndjson")
    response.headers["X-Session-ID"] = pipeline.session_id
    return response



# ── VSS (Video Search & Summarization) compatibility ────────────────────────
#
# GET /models and POST /transcriptions match the contract exposed by the
# previous Edge AI Libraries release, which is what VSS's pipeline-manager
# (sample-applications/video-search-and-summarization) calls. VSS always
# supplies a MinIO source (minio_bucket/video_id/video_name) rather than a
# direct file upload, and reads the transcript back out of that same MinIO
# bucket itself, so this service must push the transcript there too — see
# utils/minio_handler.py.
#
# NOTE: `device`/`model_name` are accepted for request-shape parity but are
# currently informational only — this service transcribes with its single
# configured ASR model/device (config.models.asr). Flagged for VSS/infra
# team coordination if a multi-model picker is required end-to-end.

@router.get("/models", response_model=AvailableModelsResponse, tags=["VSS API"])
def vss_available_models():
    """List ASR model(s) available for VSS transcription requests."""
    model_id = config.models.asr.name
    return AvailableModelsResponse(
        models=[
            WhisperModelInfo(
                model_id=model_id,
                display_name=model_id,
                description=f"{config.models.asr.provider} provider on {config.models.asr.device}",
            )
        ],
        default_model=model_id,
    )


@router.post("/transcriptions", response_model=VssTranscriptionResponse, tags=["VSS API"])
async def vss_transcribe(
    request: Annotated[VssTranscriptionForm, Depends()],
    language: Annotated[str | None, Query(description="_(Optional)_ Language hint for transcription.")] = None,
):
    """VSS-compatible transcription endpoint.

    Accepts either a direct file upload or a MinIO source
    (minio_bucket/video_id/video_name), transcribes it, and returns a
    transcript_path. When a MinIO source is used, the transcript is also
    uploaded back into that bucket so VSS can read it directly, matching the
    previous release's behavior.
    """
    has_file = request.file is not None and getattr(request.file, "filename", None)
    has_minio_source = request.has_minio_source()

    if has_file and has_minio_source:
        raise HTTPException(status_code=400, detail="Provide either 'file' or MinIO parameters, not both")
    if not has_file and not has_minio_source:
        raise HTTPException(
            status_code=400,
            detail="Provide 'file' or all of 'minio_bucket', 'video_id' and 'video_name'",
        )

    job_id = generate_session_id()

    if has_minio_source:
        if not MinioHandler.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MinIO source requested but MinIO is not configured on this service "
                       "(minio.endpoint is empty) — coordinate with the VSS/infra team to "
                       "provision MinIO connection details.",
            )
        safe_video_id = os.path.basename(request.video_id)
        safe_video_name = os.path.basename(request.video_name)
        if safe_video_id != request.video_id or safe_video_id in {"", ".", ".."}:
            raise HTTPException(status_code=400, detail="Invalid video_id")
        if safe_video_name != request.video_name or safe_video_name in {"", ".", ".."}:
            raise HTTPException(status_code=400, detail="Invalid video_name")
        video_path, error = await MinioHandler.get_video_from_minio(
            request.minio_bucket, safe_video_id, safe_video_name
        )
        if error or not video_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source video not found: {error}",
            )
        filename = request.video_name
        filepath = str(video_path)
    else:
        filename, filepath = save_audio_file(request.file, session_id=job_id)
        if not os.path.isfile(filepath):
            logger.error("Uploaded file was not persisted at expected path: %s", filepath)
            raise HTTPException(status_code=400, detail="Uploaded file could not be saved")

    if request.model_name and request.model_name != config.models.asr.name:
        logger.warning(
            "VSS requested model_name=%s but this service only supports the configured "
            "model %s; proceeding with the configured model.",
            request.model_name, config.models.asr.name,
        )

    try:
        pipeline = Pipeline(session_id=job_id, append_to_session=False)
        result = await run_in_threadpool(
            pipeline.transcribe,
            SimpleNamespace(audio_filename=filepath, source_type=AudioSource.AUDIO_FILE),
            language=language,
        )
    except Exception:
        logger.exception("VSS transcription failed for job %s", job_id)
        return VssTranscriptionResponse(
            status=TranscriptionStatus.FAILED,
            message="Transcription failed",
            job_id=job_id,
            video_name=filename,
        )

    transcript_path = os.path.join(get_session_dir(job_id), "transcription.txt")

    if has_minio_source:
        object_name = f"{safe_video_id}/{Path(filename).stem}.txt"
        uploaded, upload_error = await run_in_threadpool(
            MinioHandler.save_transcript_to_minio,
            Path(transcript_path),
            request.minio_bucket,
            object_name,
        )
        if not uploaded:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Transcription succeeded but failed to store transcript in MinIO: {upload_error}",
            )
        transcript_path = f"minio://{request.minio_bucket}/{object_name}"
        try:
            os.remove(filepath)
        except OSError:
            logger.warning("Failed to remove downloaded MinIO file %s", filepath, exc_info=True)

    return VssTranscriptionResponse(
        status=TranscriptionStatus.COMPLETED,
        message="Transcription completed successfully",
        job_id=job_id,
        transcript_path=transcript_path,
        video_name=filename,
        video_duration=result.get("duration"),
    )


@router.get("/devices")
def list_audio_devices():
    result = subprocess.run(
        ["arecord", "-l"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    audio_devices = re.findall(r"card\s+(\d+):\s+([^,]+),\s+device\s+(\d+):\s+([^\n]+)", result.stdout)
    formatted_devices = [
        f"hw:{card},{device} ({card_name.strip()} - {device_name.strip()})"
        for card, card_name, device, device_name in audio_devices
    ]

    return {"devices": formatted_devices}