# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""OpenAI Realtime-compatible WebSocket transcription endpoint.

Enables *continuous* audio streaming into the Audio Analyzer. Clients push
PCM16 frames with ``input_audio_buffer.append``; server-side VAD splits the
stream into utterances, each of which is transcribed by the existing
``Pipeline`` and returned as delta/completed events.

This replaces the previously unreachable ALSA microphone path
(``chunk_audiostream_by_silence``), which required a ``hw:x,y`` capture device
and therefore could not work in typical container deployments.

Client -> server events
    session.update              Update language / VAD / audio format.
    input_audio_buffer.append   {"audio": "<base64 pcm16>"}
    input_audio_buffer.commit   Force-close the current utterance.
    input_audio_buffer.preview  Non-destructive: transcribe everything
                                 buffered since the last real commit WITHOUT
                                 clearing it, so a caller can get a fresh,
                                 full-context transcript snapshot mid-speech
                                 without waiting for (or costing) a real
                                 commit. See ``_preview_utterance``.
    input_audio_buffer.clear    Discard buffered audio.

Server -> client events
    transcription_session.created / .updated
    input_audio_buffer.speech_started / .speech_stopped / .committed / .cleared
    conversation.item.input_audio_transcription.delta
    conversation.item.input_audio_transcription.completed
    conversation.item.input_audio_transcription.preview
    error
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import uuid
from types import SimpleNamespace

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from dto.audiosource import AudioSource
from pipeline import Pipeline
from utils.app_paths import get_session_dir
from utils.config_loader import config
from utils.pcm_audio import (
    DEFAULT_PREFIX_PADDING_MS,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SILENCE_DURATION_MS,
    DEFAULT_VAD_THRESHOLD,
    EnergyVad,
    PcmStreamBuffer,
    pcm_duration_sec,
    write_wav,
)
from utils.session_manager import generate_session_id

logger = logging.getLogger(__name__)

router = APIRouter()

# Guard rails for a long-lived socket.
MAX_APPEND_BYTES = 5 * 1024 * 1024          # per-message cap
MAX_UTTERANCE_SECONDS = 120.0               # force-commit runaway speech
MIN_UTTERANCE_SECONDS = 0.20                # ignore blips too short to transcribe
MIN_PREVIEW_SECONDS = 0.20                  # same floor for non-destructive previews
# Bound each preview's decode cost so it doesn't grow with utterance length.
# Without this, a preview re-transcribes the WHOLE buffered utterance every
# tick -- on a several-second utterance the final preview (the one covering
# the customer's actual last word) takes 700ms+ on CPU, dwarfing the ~160ms
# per-utterance figure a bounded-window decode achieves. Previews only need
# to resolve recent speech (earlier portions are already captured by the
# adaptive-pause flush's real commits), so trimming to a trailing window is
# safe for the preview's purpose (endpoint-completeness heuristic + fresh
# transcript-ready signal) even though it is never used for the persisted
# transcript.
PREVIEW_MAX_WINDOW_SECONDS = 2.0
SUPPORTED_AUDIO_FORMAT = "pcm16"

# Standard Whisper/distil-whisper naming convention: a ".en" suffix marks an
# English-only checkpoint (e.g. "distil-whisper/distil-small.en") that has no
# language token at all. openvino_genai.WhisperPipeline raises
# "Cannot specify 'language' for not multilingual model." if ANY language
# hint is forwarded to one of these -- not just a non-English one. Multi-
# lingual checkpoints (e.g. "whisper-small") have no such suffix and require
# (or at least accept) an explicit language hint. This must be checked
# against whichever model config.models.asr.name actually resolves to,
# because that is deployment-configurable (see config.yaml).
FINAL_MODEL_IS_ENGLISH_ONLY = str(getattr(config.models.asr, "name", "")).endswith(".en")


class RealtimeSession:
    """Per-connection state for a realtime transcription socket."""

    def __init__(self, session_id: str, language: str | None):
        self.session_id = session_id
        self.language = language
        # Speaker/diarization scope, set via session.update -- mirrors the
        # file-based /v1/audio/transcriptions endpoint's Form fields so the
        # two ASR paths stay at feature parity.
        self.speaker_scope_id: str | None = None
        self.diarization: bool | None = None
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.audio_format = SUPPORTED_AUDIO_FORMAT
        self.vad_enabled = True
        self.threshold = DEFAULT_VAD_THRESHOLD
        self.silence_duration_ms = DEFAULT_SILENCE_DURATION_MS
        self.prefix_padding_ms = DEFAULT_PREFIX_PADDING_MS
        self.buffer = PcmStreamBuffer(sample_rate=self.sample_rate)
        self.vad = EnergyVad(
            sample_rate=self.sample_rate,
            threshold=self.threshold,
            silence_duration_ms=self.silence_duration_ms,
            prefix_padding_ms=self.prefix_padding_ms,
        )
        # Serializes transcription so utterances are emitted in order.
        self.lock = asyncio.Lock()
        self.utterance_index = 0
        # Separate counter for non-destructive previews (see
        # input_audio_buffer.preview) -- kept independent of utterance_index
        # so real commit sequencing is unaffected by preview activity.
        self.preview_index = 0

    def rebuild_audio_state(self) -> None:
        self.buffer = PcmStreamBuffer(sample_rate=self.sample_rate)
        self.vad = EnergyVad(
            sample_rate=self.sample_rate,
            threshold=self.threshold,
            silence_duration_ms=self.silence_duration_ms,
            prefix_padding_ms=self.prefix_padding_ms,
        )

    def config_payload(self) -> dict:
        return {
            "id": self.session_id,
            "object": "realtime.transcription_session",
            "input_audio_format": self.audio_format,
            "sample_rate": self.sample_rate,
            "input_audio_transcription": {
                "model": config.models.asr.name,
                "language": self.language,
            },
            "turn_detection": None if not self.vad_enabled else {
                "type": "server_vad",
                "threshold": self.threshold,
                "prefix_padding_ms": self.prefix_padding_ms,
                "silence_duration_ms": self.silence_duration_ms,
            },
        }


async def _send(ws: WebSocket, payload: dict) -> None:
    await ws.send_text(json.dumps(payload))


async def _send_error(ws: WebSocket, message: str, code: str = "invalid_request_error") -> None:
    await _send(ws, {"type": "error", "error": {"type": code, "message": message}})


def _apply_session_update(session: RealtimeSession, patch: dict) -> None:
    """Apply a session.update payload; audio-affecting changes rebuild state."""
    audio_dirty = False

    audio_format = patch.get("input_audio_format")
    if isinstance(audio_format, str) and audio_format:
        if audio_format != SUPPORTED_AUDIO_FORMAT:
            raise ValueError(
                f"Unsupported input_audio_format '{audio_format}'. Only '{SUPPORTED_AUDIO_FORMAT}' is supported."
            )
        session.audio_format = audio_format

    sample_rate = patch.get("sample_rate")
    if sample_rate is not None:
        rate = int(sample_rate)
        if not 8000 <= rate <= 48000:
            raise ValueError("sample_rate must be between 8000 and 48000")
        session.sample_rate = rate
        audio_dirty = True

    transcription = patch.get("input_audio_transcription")
    if isinstance(transcription, dict) and "language" in transcription:
        language = transcription.get("language")
        session.language = language or None

    if "speaker_scope_id" in patch:
        session.speaker_scope_id = patch.get("speaker_scope_id") or None

    if "diarization" in patch:
        diarization = patch.get("diarization")
        session.diarization = None if diarization is None else bool(diarization)

    if "turn_detection" in patch:
        turn_detection = patch.get("turn_detection")
        if turn_detection is None:
            session.vad_enabled = False
        else:
            if not isinstance(turn_detection, dict):
                raise ValueError("turn_detection must be an object or null")
            session.vad_enabled = True
            if "threshold" in turn_detection:
                session.threshold = float(turn_detection["threshold"])
            if "silence_duration_ms" in turn_detection:
                session.silence_duration_ms = int(turn_detection["silence_duration_ms"])
            if "prefix_padding_ms" in turn_detection:
                session.prefix_padding_ms = int(turn_detection["prefix_padding_ms"])
        audio_dirty = True

    if audio_dirty:
        pending = session.buffer.take()
        session.rebuild_audio_state()
        session.buffer.append(pending)


def _transcribe_pcm(session_id: str, pcm: bytes, sample_rate: int, language: str | None,
                    label: str, speaker_scope_id: str | None,
                    diarization: bool | None, append_to_session: bool = True) -> dict:
    """Blocking: persist the utterance as WAV and run it through the Pipeline.

    ``append_to_session=False`` (used for non-destructive previews) runs a
    throwaway Pipeline that neither reads nor writes session_state.json --
    it only ever transcribes exactly the bytes passed in, so repeated
    previews of a growing peeked buffer never corrupt or duplicate the real,
    persisted session transcript built by actual commits.
    """
    session_dir = get_session_dir(session_id)
    os.makedirs(session_dir, exist_ok=True)
    wav_path = os.path.join(session_dir, f"realtime_{label}.wav")
    write_wav(wav_path, pcm, sample_rate)

    try:
        # append_to_session accumulates transcript/sentiment across utterances so
        # the socket produces one coherent session transcript. speaker_scope_id
        # / diarization mirror the file-based endpoint for feature parity.
        pipeline = Pipeline(
            session_id=session_id,
            append_to_session=append_to_session,
            speaker_scope_id=speaker_scope_id,
            diarization=diarization,
        )
        return pipeline.transcribe(
            SimpleNamespace(audio_filename=wav_path, source_type=AudioSource.AUDIO_FILE),
            language=language,
        )
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            logger.debug("Could not remove realtime utterance file %s", wav_path, exc_info=True)


async def _commit_utterance(ws: WebSocket, session: RealtimeSession, reason: str) -> None:
    """Transcribe buffered audio and emit delta/completed events."""
    async with session.lock:
        pcm = session.buffer.take()
        duration = pcm_duration_sec(pcm, session.sample_rate)
        if not pcm or duration < MIN_UTTERANCE_SECONDS:
            # Nothing meaningful captured; stay silent rather than emitting an
            # empty transcript the client would have to filter out.
            return

        session.utterance_index += 1
        item_id = f"item_{uuid.uuid4().hex[:24]}"

        await _send(ws, {
            "type": "input_audio_buffer.committed",
            "item_id": item_id,
            "reason": reason,
        })

        try:
            result = await run_in_threadpool(
                _transcribe_pcm,
                session.session_id,
                pcm,
                session.sample_rate,
                # See FINAL_MODEL_IS_ENGLISH_ONLY above: forwarding
                # session.language to an English-only final-pool checkpoint
                # (e.g. distil-small.en) crashes openvino_genai outright, so
                # this must be forced to None in that configuration -- the
                # persisted transcript is unaffected since the model has no
                # language ambiguity to resolve.
                None if FINAL_MODEL_IS_ENGLISH_ONLY else session.language,
                f"{session.utterance_index:05d}",
                session.speaker_scope_id,
                session.diarization,
                True,  # append_to_session -- real commit, persists session state
            )
        except Exception:
            logger.exception("Realtime transcription failed for session %s", session.session_id)
            await _send_error(ws, "Transcription failed for the committed audio buffer", "server_error")
            return

        text = (result.get("text") or "").strip()
        if not text:
            return

        await _send(ws, {
            "type": "conversation.item.input_audio_transcription.delta",
            "item_id": item_id,
            "content_index": 0,
            "delta": text,
        })
        completed = {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": item_id,
            "content_index": 0,
            "transcript": text,
            # Monotonically increasing per session -- lets a client discard a
            # late/out-of-order event instead of overwriting a newer snapshot.
            "sequence": session.utterance_index,
            "segments": result.get("segments") or [],
        }
        if result.get("language"):
            completed["language"] = result["language"]
        if "sentiment_summary" in result:
            completed["sentiment_summary"] = result["sentiment_summary"]
        await _send(ws, completed)


async def _preview_utterance(ws: WebSocket, session: RealtimeSession) -> None:
    """Non-destructively transcribe everything buffered since the last real
    commit, WITHOUT clearing the buffer or touching persisted session state.

    This is what gives the client a fresh, full-context transcript snapshot
    while speech is still ongoing: unlike splitting audio into independent
    committed slices, the window always starts at the same fixed point (the
    last real commit), so Whisper always sees the whole in-progress
    utterance -- never a mid-word fragment -- and there is nothing to
    deduplicate against the persisted transcript, because nothing here is
    ever persisted.
    """
    async with session.lock:
        pcm = session.buffer.peek_tail(PREVIEW_MAX_WINDOW_SECONDS)
        duration = pcm_duration_sec(pcm, session.sample_rate)
        if not pcm or duration < MIN_PREVIEW_SECONDS:
            return

        session.preview_index += 1
        preview_index = session.preview_index

        try:
            result = await run_in_threadpool(
                _transcribe_pcm,
                session.session_id,
                pcm,
                session.sample_rate,
                # Force None here, NOT session.language: the preview pool may
                # run a different, English-only model than the final commit
                # (see config.models.asr.preview / pipeline.py's per-pool
                # model selection). openvino_genai.WhisperPipeline raises for
                # ANY language token on an English-only checkpoint, so this
                # scratch/throwaway call must never forward the session's
                # (possibly multilingual-oriented) language hint -- the real,
                # persisted commit below still gets session.language
                # unchanged.
                None,
                f"preview_{preview_index:05d}",
                session.speaker_scope_id,
                # Force False here, NOT session.diarization: preview is a
                # scratch/throwaway transcript (never persisted, no
                # speaker-filter step consumes it) used only for endpoint-
                # completeness/stability detection. Running pyannote
                # diarization on every preview call (2-7x per turn) pays its
                # full inference cost for output nobody reads -- the real,
                # persisted commit below still gets session.diarization
                # unchanged so speaker filtering keeps working there.
                False,
                False,  # append_to_session -- scratch, never persisted
            )
        except Exception:
            logger.exception("Realtime preview transcription failed for session %s", session.session_id)
            return

        text = (result.get("text") or "").strip()
        await _send(ws, {
            "type": "conversation.item.input_audio_transcription.preview",
            "sequence": preview_index,
            "transcript": text,
            "segments": result.get("segments") or [],
        })


async def _handle_append(ws: WebSocket, session: RealtimeSession, message: dict) -> None:
    audio_b64 = message.get("audio")
    if not isinstance(audio_b64, str) or not audio_b64:
        await _send_error(ws, "input_audio_buffer.append requires a base64 'audio' field")
        return

    try:
        pcm = base64.b64decode(audio_b64, validate=True)
    except (binascii.Error, ValueError):
        await _send_error(ws, "'audio' must be valid base64-encoded pcm16 data")
        return

    if len(pcm) > MAX_APPEND_BYTES:
        await _send_error(ws, f"Audio chunk exceeds {MAX_APPEND_BYTES} bytes", "invalid_request_error")
        return

    session.buffer.append(pcm)

    if session.vad_enabled:
        for event in session.vad.process(pcm):
            if event == "speech_started":
                await _send(ws, {"type": "input_audio_buffer.speech_started"})
            elif event == "speech_stopped":
                await _send(ws, {"type": "input_audio_buffer.speech_stopped"})
                await _commit_utterance(ws, session, reason="server_vad")

    # Safety valve: never let a single utterance grow without bound.
    if session.buffer.duration_sec >= MAX_UTTERANCE_SECONDS:
        await _commit_utterance(ws, session, reason="max_duration")


@router.websocket("/v1/realtime")
async def realtime_transcription(
    websocket: WebSocket,
    intent: str = Query("transcription"),
    session_id: str | None = Query(None),
    language: str | None = Query(None),
):
    """Continuous audio streaming transcription over WebSocket."""
    await websocket.accept()

    if intent != "transcription":
        await _send_error(websocket, "Only intent='transcription' is supported", "invalid_request_error")
        await websocket.close(code=1008)
        return

    session = RealtimeSession(
        session_id=session_id or generate_session_id(),
        language=language,
    )

    await _send(websocket, {
        "type": "transcription_session.created",
        "session": session.config_payload(),
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "Message must be valid JSON")
                continue
            if not isinstance(message, dict):
                await _send_error(websocket, "Message must be a JSON object")
                continue

            event_type = message.get("type")

            if event_type == "input_audio_buffer.append":
                await _handle_append(websocket, session, message)

            elif event_type == "input_audio_buffer.commit":
                await _commit_utterance(websocket, session, reason="client_commit")

            elif event_type == "input_audio_buffer.preview":
                await _preview_utterance(websocket, session)

            elif event_type == "input_audio_buffer.clear":
                session.buffer.clear()
                session.vad.reset()
                await _send(websocket, {"type": "input_audio_buffer.cleared"})

            elif event_type in ("session.update", "transcription_session.update"):
                patch = message.get("session")
                if not isinstance(patch, dict):
                    await _send_error(websocket, "session.update requires a 'session' object")
                    continue
                try:
                    _apply_session_update(session, patch)
                except (ValueError, TypeError) as exc:
                    await _send_error(websocket, str(exc))
                    continue
                await _send(websocket, {
                    "type": "transcription_session.updated",
                    "session": session.config_payload(),
                })

            elif event_type == "session.close":
                await _commit_utterance(websocket, session, reason="session_close")
                await websocket.close(code=1000)
                return

            else:
                await _send_error(websocket, f"Unsupported event type: {event_type!r}")

    except WebSocketDisconnect:
        # Flush whatever speech was captured before the client vanished.
        logger.info("Realtime client disconnected (session %s)", session.session_id)
    except Exception:
        logger.exception("Realtime socket failure (session %s)", session.session_id)
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
