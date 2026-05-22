import base64
import logging
from io import BytesIO

import soundfile as sf
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse, Response

from api.error_responses import openai_error_response
from dto.speech_dto import SpeechRequest
from pipeline import Pipeline
from utils.session_manager import generate_session_id


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/v1/audio/speech")
def generate_speech(request: SpeechRequest):
    # request.model is accepted for OpenAI API compatibility but the loaded model
    # is always the one defined in config; it cannot be switched via the request.

    try:
        request.validate_for_service()
        pipeline = Pipeline(session_id=generate_session_id())
        result = pipeline.synthesize(
            text=request.input,
            language=request.language,
            speaker=request.voice,
            instructions=request.instructions,
        )
    except ValueError as exc:
        return openai_error_response(400, str(exc), code="invalid_request")
    except RuntimeError as exc:
        logger.exception("Speech synthesis runtime failure")
        return openai_error_response(
            503,
            "Speech synthesis is temporarily unavailable",
            error_type="server_error",
            code="service_unavailable",
        )
    except Exception as exc:
        logger.exception("Unexpected speech synthesis failure")
        return openai_error_response(
            500,
            "Speech synthesis failed",
            error_type="server_error",
            code="internal_error",
        )

    audio_bytes = BytesIO()
    sf.write(audio_bytes, result["audio"], result["sampling_rate"], format="WAV")
    payload = audio_bytes.getvalue()

    if request.response_format == "json":
        return JSONResponse(
            content={
                "session_id": result["session_id"],
                "model": result["model"],
                "variant": result["variant"],
                "voice": result["speaker"],
                "language": result["language"],
                "duration": result["duration"],
                "sampling_rate": result["sampling_rate"],
                "audio_base64": base64.b64encode(payload).decode("ascii"),
            },
            status_code=status.HTTP_200_OK,
        )

    return Response(
        content=payload,
        media_type="audio/wav",
        headers={
            "X-Session-ID": result["session_id"],
            "Content-Disposition": 'inline; filename="speech.wav"',
        },
    )