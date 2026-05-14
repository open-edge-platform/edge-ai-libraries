import json
import os
import re
import subprocess
from types import SimpleNamespace

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from dto.audiosource import AudioSource
from pipeline import Pipeline
from utils.audio_util import save_audio_file
from utils.locks import audio_pipeline_lock
from utils.session_manager import resolve_requested_session_id


router = APIRouter()


@router.get("/health")
def health():
    return JSONResponse(content={"status": "ok"}, status_code=200)


@router.post("/v1/audio/transcriptions/stream")
def stream_transcribe_audio(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    language: str | None = Form(None),
    temperature: float = Form(0.0),
):
    if audio_pipeline_lock.locked():
        raise HTTPException(status_code=429, detail="Session Active, Try Later")

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