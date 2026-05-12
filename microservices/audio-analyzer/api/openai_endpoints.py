import os
from types import SimpleNamespace

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse

from dto.audiosource import AudioSource
from pipeline import Pipeline
from utils.audio_util import save_audio_file
from utils.locks import audio_pipeline_lock
from utils.session_manager import resolve_requested_session_id


router = APIRouter()


def _format_srt(segments: list[dict]) -> str:
    def timestamp(seconds: float) -> str:
        total_milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(total_milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        secs, milliseconds = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"

    blocks = []
    for index, segment in enumerate(segments, start=1):
        blocks.append(
            f"{index}\n{timestamp(segment['start'])} --> {timestamp(segment['end'])}\n{segment['text']}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _format_vtt(segments: list[dict]) -> str:
    def timestamp(seconds: float) -> str:
        total_milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(total_milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        secs, milliseconds = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}.{milliseconds:03}"

    blocks = ["WEBVTT"]
    for segment in segments:
        blocks.append(
            f"{timestamp(segment['start'])} --> {timestamp(segment['end'])}\n{segment['text']}"
        )
    return "\n\n".join(blocks) + ("\n" if len(blocks) > 1 else "")


@router.post("/v1/audio/transcriptions")
def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("whisper-1"),
    session_id: str | None = Form(None),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: str = Form("json"),
    temperature: float = Form(0.0),
):
    if audio_pipeline_lock.locked():
        raise HTTPException(status_code=429, detail="Session Active, Try Later")

    del prompt

    if model not in {"whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe"}:
        raise HTTPException(status_code=400, detail=f"Unsupported model: {model}")

    if response_format not in {"json", "text", "verbose_json", "srt", "vtt"}:
        raise HTTPException(status_code=400, detail=f"Unsupported response_format: {response_format}")

    try:
        session_id, continue_session = resolve_requested_session_id(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _, filepath = save_audio_file(file, session_id=session_id)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=400, detail=f"Audio file not found: {filepath}")

    pipeline = Pipeline(session_id=session_id, temperature=temperature, append_to_session=continue_session)

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