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
    input_audio_buffer.preview  Non-destructive: transcribe the trailing
                                 window of audio buffered since the last real
                                 commit WITHOUT clearing it, so a caller can
                                 get a best-effort progress snapshot
                                 mid-speech without waiting for (or costing)
                                 a real commit. May start mid-word — never a
                                 final transcript. See ``_preview_utterance``.
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
from utils.asr_model_capabilities import is_english_only_model
from utils.asr_pool_config import resolve_pool_config
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
from utils.session_manager import resolve_requested_session_id

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


def _language_for_pool(pool: str, language: str | None) -> str | None:
    """Drop the language hint only when the pool's model is English-only.

    English-only Whisper checkpoints (``.en`` suffix) have no language token;
    ``openvino_genai.WhisperPipeline`` raises for ANY language hint on one.
    Multilingual pools keep the caller's language, so a multilingual preview
    model is no longer forced into auto-detection.
    """
    if not language:
        return None
    model_name = resolve_pool_config(pool).name
    if is_english_only_model(model_name):
        logger.debug("Dropping language=%s for %s pool: model %s is English-only",
                     language, pool, model_name)
        return None
    return language


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
        # Guards against overlapping preview decodes. Previews deliberately
        # run OUTSIDE session.lock (see _preview_utterance), so the lock
        # cannot serialize them; without this flag a fast client could stack
        # several concurrent decodes on the preview model.
        self.preview_active = False
        # Serializes socket writes. Previews are dispatched as background
        # tasks so the receive loop keeps reading, which means a preview event
        # and a commit event can be produced by different tasks; without this
        # their frames could interleave on the wire.
        self.send_lock = asyncio.Lock()
        # Strong references to in-flight background tasks. asyncio only holds
        # weak references to tasks, so a task that nothing references can be
        # garbage collected mid-flight. Drained on disconnect/close.
        self.background_tasks: set[asyncio.Task] = set()

    def spawn(self, coro) -> asyncio.Task:
        """Run ``coro`` concurrently with the receive loop, keeping a strong ref."""
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        return task

    async def drain_background_tasks(self) -> None:
        """Cancel in-flight background work and wait for it to unwind.

        Called on every exit path. Previews are throwaway, so they are
        cancelled rather than awaited; leaving them running would let a task
        write to a closed socket.
        """
        tasks = list(self.background_tasks)
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

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


async def _send(ws: WebSocket, payload: dict, send_lock: asyncio.Lock | None = None) -> None:
    """Write one JSON event to the socket.

    Args:
        ws: The connected WebSocket.
        payload: JSON-serializable event body.
        send_lock: Serializes writes when more than one task can send on this
            socket. Previews run as background tasks (see
            ``_preview_utterance``), so a preview event and a commit event can
            otherwise be written concurrently and interleave on the wire.
            Omitted only before the session exists, when the handler is the
            sole writer.
    """
    if send_lock is None:
        await ws.send_text(json.dumps(payload))
        return
    async with send_lock:
        await ws.send_text(json.dumps(payload))


async def _send_error(ws: WebSocket, message: str, code: str = "invalid_request_error",
                      send_lock: asyncio.Lock | None = None) -> None:
    await _send(ws, {"type": "error", "error": {"type": code, "message": message}}, send_lock)


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
                    diarization: bool | None, append_to_session: bool = True,
                    pool: str = Pipeline.POOL_FINAL) -> dict:
    """Blocking: persist the utterance as WAV and run it through the Pipeline.

    The preview pool (``pool=Pipeline.POOL_PREVIEW``) runs a throwaway
    Pipeline that neither reads nor writes session_state.json -- it only ever
    transcribes exactly the bytes passed in, so repeated previews of a growing
    peeked buffer never corrupt or duplicate the real, persisted session
    transcript built by actual commits. The scratch WAV is removed in either
    case, so previews leave nothing behind on disk.

    Args:
        session_id: Session the audio belongs to.
        pcm: Raw little-endian 16-bit PCM payload.
        sample_rate: Sample rate of ``pcm``.
        language: Language hint, already filtered for the target pool.
        label: Filename suffix for the scratch WAV.
        speaker_scope_id: Stable speaker-enrollment scope key.
        diarization: Per-request narrowing override for diarization.
        append_to_session: Accumulate into the session transcript.
        pool: Which ASR model pool to run on.

    Returns:
        The pipeline's transcription result dict.
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
            pool=pool,
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
        }, send_lock=session.send_lock)

        try:
            result = await run_in_threadpool(
                _transcribe_pcm,
                session.session_id,
                pcm,
                session.sample_rate,
                # Kept unless the final pool's model is English-only -- see
                # _language_for_pool().
                _language_for_pool(Pipeline.POOL_FINAL, session.language),
                f"{session.utterance_index:05d}",
                session.speaker_scope_id,
                session.diarization,
                True,  # append_to_session -- real commit, persists session state
                Pipeline.POOL_FINAL,
            )
        except Exception:
            logger.exception("Realtime transcription failed for session %s", session.session_id)
            await _send_error(ws, "Transcription failed for the committed audio buffer", "server_error", send_lock=session.send_lock)
            return

        text = (result.get("text") or "").strip()
        if not text:
            return

        await _send(ws, {
            "type": "conversation.item.input_audio_transcription.delta",
            "item_id": item_id,
            "content_index": 0,
            "delta": text,
        }, send_lock=session.send_lock)
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
        await _send(ws, completed, send_lock=session.send_lock)


async def _preview_utterance(ws: WebSocket, session: RealtimeSession) -> None:
    """Non-destructively transcribe recent buffered audio.

    Emits a ``conversation.item.input_audio_transcription.preview`` event for
    the trailing ``PREVIEW_MAX_WINDOW_SECONDS`` of audio buffered since the
    last real commit, without clearing the buffer or touching persisted
    session state. Nothing produced here is ever persisted, so there is
    nothing to deduplicate against the real transcript.

    Note that the trailing window is a plain time cut, not a VAD boundary:
    a preview may begin mid-word, so clients must treat the transcript as a
    best-effort progress signal and never as a final transcript.

    A commit is never delayed by a preview. ``session.lock`` is held only long
    enough to copy the trailing PCM out of the buffer; the decode itself --
    the part that takes hundreds of milliseconds -- runs with the lock
    RELEASED, operating on that private copy. An in-flight decode cannot be
    cancelled once handed to the threadpool, so not holding the lock across it
    is what actually keeps a concurrent commit from queueing behind it.

    The preview is additionally skipped outright when a commit already holds
    the lock, and when another preview is still decoding.

    A preview whose decode finishes after a commit landed is discarded rather
    than emitted, so a stale snapshot never arrives after the authoritative
    transcript for the same audio.
    """
    if session.lock.locked() or session.preview_active:
        # A real commit is decoding, or an earlier preview has not finished.
        # Previews are best-effort progress ticks, so dropping this one is
        # strictly better than piling work onto the ASR backend.
        logger.debug("Skipping preview for session %s: decode already in flight", session.session_id)
        return

    # Snapshot under the lock, decode outside it. peek_tail() returns an
    # independent bytes copy, so the decode has no further need for the lock
    # and a commit arriving mid-decode acquires it immediately.
    async with session.lock:
        pcm = session.buffer.peek_tail(PREVIEW_MAX_WINDOW_SECONDS)
        duration = pcm_duration_sec(pcm, session.sample_rate)
        if not pcm or duration < MIN_PREVIEW_SECONDS:
            return

        session.preview_index += 1
        preview_index = session.preview_index
        # Generation marker: if a commit consumes the buffer while this
        # preview decodes, the snapshot describes audio the client has
        # already received a final transcript for.
        commit_generation = session.utterance_index
        session.preview_active = True

    try:
        result = await run_in_threadpool(
            _transcribe_pcm,
            session.session_id,
            pcm,
            session.sample_rate,
            # Resolved against the PREVIEW pool's model, which may differ
            # from the final pool's -- a multilingual preview model keeps
            # the caller's language instead of falling back to
            # auto-detection.
            _language_for_pool(Pipeline.POOL_PREVIEW, session.language),
            f"preview_{preview_index:05d}",
            session.speaker_scope_id,
            # Force False, NOT session.diarization: a preview is a scratch
            # transcript (never persisted, no speaker-filter step consumes
            # it). Running pyannote on every preview tick pays its full
            # inference cost for output nobody reads -- the real commit
            # still gets session.diarization unchanged.
            False,
            False,  # append_to_session -- scratch, never persisted
            Pipeline.POOL_PREVIEW,
        )
    except Exception:
        logger.exception("Realtime preview transcription failed for session %s", session.session_id)
        return
    finally:
        session.preview_active = False

    if session.utterance_index != commit_generation:
        logger.debug(
            "Dropping stale preview %d for session %s: commit landed mid-decode",
            preview_index, session.session_id,
        )
        return

    text = (result.get("text") or "").strip()
    await _send(ws, {
        "type": "conversation.item.input_audio_transcription.preview",
        "sequence": preview_index,
        "transcript": text,
        "segments": result.get("segments") or [],
    }, send_lock=session.send_lock)


async def _handle_append(ws: WebSocket, session: RealtimeSession, message: dict) -> None:
    audio_b64 = message.get("audio")
    if not isinstance(audio_b64, str) or not audio_b64:
        await _send_error(ws, "input_audio_buffer.append requires a base64 'audio' field", send_lock=session.send_lock)
        return

    try:
        pcm = base64.b64decode(audio_b64, validate=True)
    except (binascii.Error, ValueError):
        await _send_error(ws, "'audio' must be valid base64-encoded pcm16 data", send_lock=session.send_lock)
        return

    if len(pcm) > MAX_APPEND_BYTES:
        await _send_error(ws, f"Audio chunk exceeds {MAX_APPEND_BYTES} bytes", "invalid_request_error", send_lock=session.send_lock)
        return

    session.buffer.append(pcm)

    if session.vad_enabled:
        for event in session.vad.process(pcm):
            if event == "speech_started":
                await _send(ws, {"type": "input_audio_buffer.speech_started"}, send_lock=session.send_lock)
            elif event == "speech_stopped":
                await _send(ws, {"type": "input_audio_buffer.speech_stopped"}, send_lock=session.send_lock)
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

    try:
        # Mirrors the HTTP endpoints' validation so a client-supplied session_id
        # can never be joined into STORAGE_ROOT unsanitized (path traversal / absolute-path guard).
        resolved_session_id, _ = resolve_requested_session_id(session_id)
    except ValueError as exc:
        await _send_error(websocket, str(exc), "invalid_request_error")
        await websocket.close(code=1008)
        return

    session = RealtimeSession(
        session_id=resolved_session_id,
        language=language,
    )

    await _send(websocket, {
        "type": "transcription_session.created",
        "session": session.config_payload(),
    }, send_lock=session.send_lock)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "Message must be valid JSON", send_lock=session.send_lock)
                continue
            if not isinstance(message, dict):
                await _send_error(websocket, "Message must be a JSON object", send_lock=session.send_lock)
                continue

            event_type = message.get("type")

            if event_type == "input_audio_buffer.append":
                await _handle_append(websocket, session, message)

            elif event_type == "input_audio_buffer.commit":
                await _commit_utterance(websocket, session, reason="client_commit")

            elif event_type == "input_audio_buffer.preview":
                # Dispatched, NOT awaited. Awaiting here would stop the
                # receive loop for the duration of the decode, so a commit --
                # or an append that triggers a VAD commit -- would sit unread
                # until the preview finished. Releasing session.lock during
                # the decode is not sufficient on its own: the delay simply
                # moves from the lock to this loop.
                session.spawn(_preview_utterance(websocket, session))

            elif event_type == "input_audio_buffer.clear":
                session.buffer.clear()
                session.vad.reset()
                await _send(websocket, {"type": "input_audio_buffer.cleared"}, send_lock=session.send_lock)

            elif event_type in ("session.update", "transcription_session.update"):
                patch = message.get("session")
                if not isinstance(patch, dict):
                    await _send_error(websocket, "session.update requires a 'session' object", send_lock=session.send_lock)
                    continue
                try:
                    _apply_session_update(session, patch)
                except (ValueError, TypeError) as exc:
                    await _send_error(websocket, str(exc), send_lock=session.send_lock)
                    continue
                await _send(websocket, {
                    "type": "transcription_session.updated",
                    "session": session.config_payload(),
                }, send_lock=session.send_lock)

            elif event_type == "session.close":
                # Drain first: a preview still decoding would otherwise try to
                # write to an already-closed socket.
                await session.drain_background_tasks()
                await _commit_utterance(websocket, session, reason="session_close")
                await websocket.close(code=1000)
                return

            else:
                await _send_error(websocket, f"Unsupported event type: {event_type!r}", send_lock=session.send_lock)

    except WebSocketDisconnect:
        # Flush whatever speech was captured before the client vanished.
        logger.info("Realtime client disconnected (session %s)", session.session_id)
    except Exception:
        logger.exception("Realtime socket failure (session %s)", session.session_id)
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
    finally:
        # Covers every exit path, including the `return` above and an
        # exception mid-loop: no preview task may outlive the connection.
        await session.drain_background_tasks()
