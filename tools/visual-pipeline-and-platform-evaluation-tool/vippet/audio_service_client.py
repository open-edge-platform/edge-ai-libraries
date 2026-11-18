# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
import re
from time import perf_counter
from typing import BinaryIO

import httpx

from api.api_schemas import TranscriptionResponse
from audio_errors import SpeechServiceError

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_ERROR_RESPONSE_BYTES = 8 * 1024
TIMEOUT_SECONDS = 20 * 60
AUDIO_ANALYZER_URL = os.getenv("AUDIO_ANALYZER_URL", "http://audio-analyzer:8010")
TEXT_TO_SPEECH_URL = os.getenv("TEXT_TO_SPEECH_URL", "http://text-to-speech:8011")
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


def normalize_upload_filename(filename: str | None) -> str:
    """Prepare a filename for forwarding as multipart upload metadata.

    Remove Unix and Windows directory components and nonprintable characters,
    keep at most 255 characters, and use ``audio`` when no usable name remains.
    This does not validate the uploaded file contents.
    """
    basename = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    printable_basename = "".join(
        character for character in basename if character.isprintable()
    )
    return printable_basename[-255:] or "audio"


def normalize_media_type(content_type: str | None) -> str:
    """Return a bounded type/subtype token suitable for multipart metadata.

    Missing, malformed, parameterized, or overlong values become
    ``application/octet-stream``; the file contents are not inspected.
    """
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
    """Read an allowlisted error message without exposing arbitrary upstream data.

    Consume at most ``MAX_ERROR_RESPONSE_BYTES`` into the buffer and return
    ``error.message`` only if it exactly matches an allowed detail. Oversized,
    malformed, or unrecognized payloads return None for the caller's fallback.
    """
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
    """Create a speech-service client whose caller owns its async lifetime.

    Apply a five-second connection timeout and the conversion timeout, disable
    redirects, and ignore proxy and certificate settings from the environment.
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=5.0),
        trust_env=False,
        follow_redirects=False,
    )


async def call_service(
    url: str,
    *,
    files: dict[str, tuple[str, BinaryIO, str]] | None = None,
    data: dict[str, str] | None = None,
    json: dict[str, str] | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    rejected_detail: str = "The speech service rejected the input.",
    safe_rejected_details: frozenset[str] = frozenset(),
) -> tuple[httpx.Response, float]:
    """POST to a speech service with bounded buffering and sanitized failures.

    Args:
        url: Speech-service endpoint.
        files: Optional multipart uploads; streams remain owned by the caller.
        data: Optional form fields.
        json: Optional JSON request body.
        max_bytes: Maximum buffered successful response size.
        rejected_detail: Fallback message for HTTP 400, 413, and 422 responses.
        safe_rejected_details: Exact upstream messages allowed to replace the
            fallback rejection message.

    Returns:
        Buffered HTTP 200 response and elapsed time in milliseconds, including
        connection setup and response reading.

    Raises:
        SpeechServiceError: The request fails, times out, is rejected, returns
            a non-200 status, or exceeds the response limit. Messages omit
            arbitrary upstream details.
    """
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
                raise SpeechServiceError(safe_detail or rejected_detail)
            if upstream.status_code == 429:
                raise SpeechServiceError("The speech service is busy. Try again later.")
            if upstream.status_code != 200:
                logger.warning("Speech service returned HTTP %s", upstream.status_code)
                raise SpeechServiceError(
                    "The speech service failed to process the request."
                )
            content = bytearray()
            async for chunk in upstream.aiter_bytes():
                if len(content) + len(chunk) > max_bytes:
                    raise SpeechServiceError(
                        "The speech service response exceeded the size limit."
                    )
                content.extend(chunk)
            result = httpx.Response(
                200, content=bytes(content), headers=upstream.headers
            )
            return result, (perf_counter() - started_at) * 1000
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise SpeechServiceError(
            "Speech conversion timed out. Try a shorter input."
        ) from exc
    except httpx.HTTPError as exc:
        raise SpeechServiceError("The speech service is unavailable.") from exc


async def execute_transcription(
    file: BinaryIO,
    filename: str,
    content_type: str,
    language: str,
    device: str,
) -> tuple[str, float]:
    """Transcribe an audio stream using the selected language and device.

    Normalize upload metadata, limit the response to 128 KiB, and validate the
    JSON body with ``TranscriptionResponse``. The caller retains ownership of
    the stream, which is read from its current position.

    Returns:
        Recognized text and speech-service round-trip time in milliseconds.

    Raises:
        SpeechServiceError: Service communication fails or the transcription
            response does not satisfy the expected schema.
    """
    upstream, service_round_trip_ms = await call_service(
        f"{AUDIO_ANALYZER_URL.rstrip('/')}/v1/audio/transcriptions",
        files={
            "file": (
                normalize_upload_filename(filename),
                file,
                normalize_media_type(content_type),
            )
        },
        data={
            "language": language,
            "response_format": "json",
            "temperature": "0",
            "device": device,
        },
        max_bytes=128 * 1024,
        rejected_detail="The selected speech-to-text device is unavailable.",
        safe_rejected_details=SAFE_AUDIO_VALIDATION_DETAILS,
    )
    try:
        result = TranscriptionResponse.model_validate(upstream.json())
    except ValueError as exc:
        raise SpeechServiceError(
            "The speech service returned an invalid transcription."
        ) from exc
    return result.text, service_round_trip_ms


async def execute_synthesis(
    text: str,
    voice: str,
    device: str,
) -> tuple[bytes, float]:
    """Synthesize WAV speech using the selected voice and inference device.

    Check the response media type, minimum length, and RIFF/WAVE markers before
    returning the payload. These checks do not fully decode or validate audio.

    Returns:
        WAV bytes and speech-service round-trip time in milliseconds.

    Raises:
        SpeechServiceError: Service communication fails or the response fails
            the expected WAV header checks.
    """
    upstream, service_round_trip_ms = await call_service(
        f"{TEXT_TO_SPEECH_URL.rstrip('/')}/v1/audio/speech",
        json={
            "input": text,
            "voice": voice,
            "response_format": "wav",
            "device": device,
        },
        rejected_detail="The selected text-to-speech device is unavailable.",
    )
    content = upstream.content
    if (
        upstream.headers.get("content-type", "").split(";")[0] != "audio/wav"
        or len(content) < 44
        or content[:4] != b"RIFF"
        or content[8:12] != b"WAVE"
    ):
        raise SpeechServiceError("The speech service returned invalid audio.")
    return content, service_round_trip_ms
