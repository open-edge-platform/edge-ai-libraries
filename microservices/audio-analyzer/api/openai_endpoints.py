import json
import logging
import os
from types import SimpleNamespace

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from components.asr.diarization.speaker_profiles import SpeakerProfileError, build_speaker_options
from dto.audiosource import AudioSource
from dto.transcription_dto import validate_transcription_options
from pipeline import Pipeline
from utils.asr_model_capabilities import is_english_only_model
from utils.config_loader import config
from utils.openvino_runtime_validation import resolve_asr_device
from utils.audio_util import save_audio_file
from utils.session_manager import resolve_requested_session_id
from utils.subtitle_format import format_srt as _format_srt, format_vtt as _format_vtt


router = APIRouter()
logger = logging.getLogger(__name__)


def _sse_transcription_events(pipeline: Pipeline, filepath: str, language: str | None):
    """Yield OpenAI-compatible SSE frames for a streamed transcription.

    Emits `transcript.text.delta` per transcribed chunk, a final
    `transcript.text.done`, then the `[DONE]` sentinel — matching the event
    shape OpenAI documents for `POST /v1/audio/transcriptions` with
    `stream=true`, so official OpenAI SDKs can consume this endpoint.
    """
    request = SimpleNamespace(audio_filename=filepath, source_type=AudioSource.AUDIO_FILE)

    for event in pipeline.stream_transcribe(request, language=language):
        if event.get("event") == "transcription.chunk":
            delta = (event.get("text") or "").strip()
            if delta:
                yield f"data: {json.dumps({'type': 'transcript.text.delta', 'delta': delta})}\n\n"
        elif event.get("event") == "transcription.completed":
            done: dict = {
                "type": "transcript.text.done",
                "text": (event.get("text") or "").strip(),
            }
            if event.get("language"):
                done["language"] = event["language"]
            if event.get("duration") is not None:
                done["duration"] = event["duration"]
            if "sentiment_summary" in event:
                done["sentiment_summary"] = event["sentiment_summary"]
            yield f"data: {json.dumps(done)}\n\n"

    yield "data: [DONE]\n\n"


def _speaker_options(diarization: bool | None, **fields):
    """Validated opt-in speaker options; None keeps per-chunk diarization (400 on bad input)."""
    diar_cfg = getattr(config.models, "diarization", None)
    try:
        options = build_speaker_options(
            configured_mode=getattr(diar_cfg, "mode", None),
            configured_threshold=getattr(diar_cfg, "speaker_match_threshold", None),
            voice_enrollment_enabled=bool(getattr(diar_cfg, "voice_enrollment_enabled", False)),
            **fields,
        )
    except SpeakerProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    diarization_active = bool(config.models.asr.diarization) and diarization is not False
    if options is None or diarization_active:
        return options
    # A deployment default of mode=file does not apply when diarization is off.
    if any(value is not None for value in fields.values()):
        raise HTTPException(
            status_code=400,
            detail="Speaker options need diarization: set models.asr.diarization=true and do not send diarization=false",
        )
    return None


@router.post("/v1/audio/transcriptions")
def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    session_id: str | None = Form(None),
    speaker_scope_id: str | None = Form(None),
    language: str | None = Form("en"),
    prompt: str | None = Form(None),
    response_format: str = Form("json"),
    temperature: float = Form(0.0),
    stream: bool = Form(False),
    diarization: bool | None = Form(None),
    device: str | None = Form(None),
    diarization_mode: str | None = Form(None),
    num_speakers: int | None = Form(None),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
    speaker_profiles: str | None = Form(None),
    unknown_speaker_label: str | None = Form(None),
    speaker_match_threshold: float | None = Form(None),
):
    language, _ = validate_transcription_options(
        temperature=temperature,
        language=language,
        prompt=prompt,
        model=model,
        response_format=response_format,
    )
    speaker_options = _speaker_options(
        diarization,
        mode=diarization_mode,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        speaker_profiles=speaker_profiles,
        unknown_speaker_label=unknown_speaker_label,
        speaker_match_threshold=speaker_match_threshold,
    )

    try:
        session_id, continue_session = resolve_requested_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    requested_device = device or config.models.asr.device
    try:
        resolved_device = resolve_asr_device(
            config.models.asr.provider,
            config.models.asr.name,
            requested_device,
        )
    except RuntimeError as exc:
        logger.warning("Rejected ASR device %s: %s", requested_device, exc)
        raise HTTPException(
            status_code=400,
            detail="Requested ASR device is unavailable or unsupported.",
        ) from exc

    _, filepath = save_audio_file(file, session_id=session_id)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=400, detail=f"Audio file not found: {filepath}")

    # The file-based endpoint is always a real, persisted transcription, so it
    # always runs on the final pool -- including the first call of a brand-new
    # session, which also has continue_session=False.
    pipeline = Pipeline(
        session_id=session_id,
        temperature=temperature,
        append_to_session=continue_session,
        speaker_scope_id=speaker_scope_id,
        diarization=diarization,
        device=resolved_device,
        pool=Pipeline.POOL_FINAL,
        speaker_options=speaker_options,
    )
    if language and is_english_only_model(pipeline.asr_model_name):
        # English-only Whisper checkpoints (".en" suffix) carry no language
        # token at all; openvino_genai.WhisperPipeline raises for ANY language
        # hint on one, not just a non-English one. Drop the hint for those
        # models only -- multilingual deployments keep the caller's language.
        logger.debug(
            "Dropping language=%s: model %s is English-only", language, pipeline.asr_model_name
        )
        language = None

    if stream:
        # OpenAI only defines streaming for the JSON response formats.
        if response_format not in ("json", "verbose_json"):
            raise HTTPException(
                status_code=400,
                detail=f"stream=true is not supported with response_format='{response_format}'",
            )
        response = StreamingResponse(
            _sse_transcription_events(pipeline, filepath, language),
            media_type="text/event-stream",
        )
        response.headers["X-Session-ID"] = pipeline.session_id
        response.headers["Cache-Control"] = "no-cache"
        return response

    try:
        result = pipeline.transcribe(
            SimpleNamespace(
                audio_filename=filepath,
                source_type=AudioSource.AUDIO_FILE,
            ),
            language=language,
        )
    except SpeakerProfileError as exc:
        # Profiles whose embeddings do not fit the diarization model.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if response_format == "text":
        response = PlainTextResponse(result["text"])
        response.headers["X-Session-ID"] = pipeline.session_id
        return response
    if response_format == "json":
        payload: dict = {"text": result["text"]}
        if "sentiment_summary" in result:
            payload["sentiment_summary"] = result["sentiment_summary"]
        response = JSONResponse(content=payload, status_code=status.HTTP_200_OK)
        response.headers["X-Session-ID"] = pipeline.session_id
        return response
    if response_format == "srt":
        response = PlainTextResponse(_format_srt(result["segments"]), media_type="text/plain; charset=utf-8")
        response.headers["X-Session-ID"] = pipeline.session_id
        return response
    if response_format == "vtt":
        response = PlainTextResponse(_format_vtt(result["segments"]), media_type="text/vtt; charset=utf-8")
        response.headers["X-Session-ID"] = pipeline.session_id
        return response

    response = JSONResponse(content=result, status_code=status.HTTP_200_OK)
    response.headers["X-Session-ID"] = pipeline.session_id
    return response