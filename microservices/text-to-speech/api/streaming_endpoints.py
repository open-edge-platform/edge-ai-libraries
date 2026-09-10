"""Server-Sent Events endpoint for phrase-level streaming synthesis.

Each event is a JSON object carrying one WAV-encoded phrase, letting a client
start playback after the first phrase instead of waiting for the whole reply.
Backends without incremental decoding emit a single event.
"""
import base64
import json
import logging
from io import BytesIO

import soundfile as sf
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.error_responses import openai_error_response
from dto.speech_dto import SpeechRequest
from pipeline import Pipeline
from utils.session_manager import generate_session_id


router = APIRouter()
logger = logging.getLogger(__name__)


def _wav_bytes(audio, sampling_rate: int) -> bytes:
    buffer = BytesIO()
    sf.write(buffer, audio, sampling_rate, format="WAV")
    return buffer.getvalue()


@router.post("/v1/audio/speech/stream")
def stream_speech(request: SpeechRequest):
    try:
        request.validate_for_service()
    except ValueError as exc:
        return openai_error_response(400, str(exc), code="invalid_request")

    session_id = generate_session_id()

    def event_stream():
        try:
            pipeline = Pipeline(session_id=session_id)
            emitted = 0
            for chunk in pipeline.synthesize_stream(
                text=request.input,
                language=request.language,
                speaker=request.voice,
                instructions=request.instructions,
            ):
                payload = {
                    "index": chunk["index"],
                    "session_id": session_id,
                    "sampling_rate": chunk["sampling_rate"],
                    "duration": chunk["duration"],
                    "voice": chunk["speaker"],
                    "language": chunk["language"],
                    "audio_base64": base64.b64encode(_wav_bytes(chunk["audio"], chunk["sampling_rate"])).decode("ascii"),
                }
                emitted += 1
                yield f"data: {json.dumps(payload)}\n\n"
            if emitted == 0:
                yield f"data: {json.dumps({'error': 'Input text contains no pronounceable characters'})}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        except Exception:
            logger.exception("Streaming speech synthesis failed")
            yield f"data: {json.dumps({'error': 'Speech synthesis failed'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Session-ID": session_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
