import json
import os
from types import SimpleNamespace

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from dto.audiosource import AudioSource
from dto.transcription_dto import validate_transcription_options
from pipeline import Pipeline
from utils.audio_util import save_audio_file
from utils.session_manager import resolve_requested_session_id
from utils.subtitle_format import format_srt as _format_srt, format_vtt as _format_vtt


router = APIRouter()


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
):
    language, _ = validate_transcription_options(
        temperature=temperature,
        language=language,
        prompt=prompt,
        model=model,
        response_format=response_format,
    )

    try:
        session_id, continue_session = resolve_requested_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _, filepath = save_audio_file(file, session_id=session_id)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=400, detail=f"Audio file not found: {filepath}")

    pipeline = Pipeline(
        session_id=session_id,
        temperature=temperature,
        append_to_session=continue_session,
        speaker_scope_id=speaker_scope_id,
    )

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

    result = pipeline.transcribe(
        SimpleNamespace(
            audio_filename=filepath,
            source_type=AudioSource.AUDIO_FILE,
        ),
        language=language,
    )

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