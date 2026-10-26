# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for OpenAI-compatible SSE streaming and the realtime WebSocket API."""
import asyncio
import base64
import json
import math
import os
import struct
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from api import realtime_endpoints
from pipeline import Pipeline


def _pcm16_tone(duration_sec: float, sample_rate: int = 16000, amplitude: float = 0.4) -> bytes:
    """Loud sine wave — reads as speech to the energy VAD."""
    frames = int(duration_sec * sample_rate)
    return b"".join(
        struct.pack("<h", int(amplitude * 32767 * math.sin(2 * math.pi * 440 * (i / sample_rate))))
        for i in range(frames)
    )


def _pcm16_silence(duration_sec: float, sample_rate: int = 16000) -> bytes:
    return b"\x00\x00" * int(duration_sec * sample_rate)


def _b64(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode("ascii")


class OpenAiSseStreamingTests(unittest.TestCase):
    """POST /v1/audio/transcriptions with stream=true must emit OpenAI SSE."""

    def _run(self, response_format="json"):
        stream_events = [
            {"event": "transcription.chunk", "text": "Hello", "segments": []},
            {"event": "transcription.chunk", "text": "world", "segments": []},
            {
                "event": "transcription.completed",
                "text": "Hello\nworld",
                "language": "en",
                "duration": 4.2,
                "segments": [],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            saved = os.path.join(tmpdir, "clip.wav")
            with open(saved, "wb") as handle:
                handle.write(b"fake-audio")

            with patch("main.ensure_model"), patch("main.preload_models"), \
                 patch("api.openai_endpoints.save_audio_file", return_value=("clip.wav", saved)), \
                 patch("api.openai_endpoints.Pipeline") as mock_pipeline_cls:
                mock_pipeline_cls.return_value.session_id = "sess-1"
                mock_pipeline_cls.return_value.stream_transcribe.return_value = iter(stream_events)

                with TestClient(main.app) as client:
                    return client.post(
                        "/v1/audio/transcriptions",
                        data={"stream": "true", "response_format": response_format},
                        files={"file": ("clip.wav", b"fake-audio", "audio/wav")},
                    )

    def test_emits_openai_sse_event_sequence(self):
        response = self._run()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(response.headers["X-Session-ID"], "sess-1")

        frames = [line[len("data: "):] for line in response.text.splitlines()
                  if line.startswith("data: ")]
        self.assertEqual(frames[-1], "[DONE]")

        parsed = [json.loads(f) for f in frames[:-1]]
        self.assertEqual([p["type"] for p in parsed],
                         ["transcript.text.delta", "transcript.text.delta", "transcript.text.done"])
        self.assertEqual(parsed[0]["delta"], "Hello")
        self.assertEqual(parsed[1]["delta"], "world")
        self.assertEqual(parsed[2]["text"], "Hello\nworld")
        self.assertEqual(parsed[2]["language"], "en")

    def test_rejects_stream_with_incompatible_response_format(self):
        response = self._run(response_format="srt")
        self.assertEqual(response.status_code, 400)

    def test_non_streaming_request_still_returns_json(self):
        result = {"text": "hello", "segments": [], "language": "en"}
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = os.path.join(tmpdir, "clip.wav")
            with open(saved, "wb") as handle:
                handle.write(b"fake-audio")

            with patch("main.ensure_model"), patch("main.preload_models"), \
                 patch("api.openai_endpoints.save_audio_file", return_value=("clip.wav", saved)), \
                 patch("api.openai_endpoints.Pipeline") as mock_pipeline_cls:
                mock_pipeline_cls.return_value.session_id = "sess-2"
                mock_pipeline_cls.return_value.transcribe.return_value = result

                with TestClient(main.app) as client:
                    response = client.post(
                        "/v1/audio/transcriptions",
                        files={"file": ("clip.wav", b"fake-audio", "audio/wav")},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "hello")


class RealtimeWebSocketTests(unittest.TestCase):
    """WS /v1/realtime must speak the OpenAI Realtime transcription events."""

    def test_session_created_on_connect(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    created = ws.receive_json()

        self.assertEqual(created["type"], "transcription_session.created")
        self.assertEqual(created["session"]["input_audio_format"], "pcm16")
        self.assertEqual(created["session"]["turn_detection"]["type"], "server_vad")

    def test_rejects_unsupported_intent(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=conversation") as ws:
                    message = ws.receive_json()

        self.assertEqual(message["type"], "error")

    def test_rejects_path_traversal_session_id(self):
        """A crafted session_id must never reach get_session_dir()/STORAGE_ROOT unsanitized."""
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect(
                    "/v1/realtime?intent=transcription&session_id=../../etc/passwd"
                ) as ws:
                    message = ws.receive_json()

        self.assertEqual(message["type"], "error")

    def test_rejects_absolute_path_session_id(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect(
                    "/v1/realtime?intent=transcription&session_id=/etc/passwd"
                ) as ws:
                    message = ws.receive_json()

        self.assertEqual(message["type"], "error")

    def test_accepts_valid_custom_session_id(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect(
                    "/v1/realtime?intent=transcription&session_id=my-session_123"
                ) as ws:
                    created = ws.receive_json()

        self.assertEqual(created["type"], "transcription_session.created")
        self.assertEqual(created["session"]["id"], "my-session_123")

    def test_session_update_changes_language_and_vad(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({
                        "type": "session.update",
                        "session": {
                            "sample_rate": 24000,
                            "input_audio_transcription": {"language": "fr"},
                            "turn_detection": {"threshold": 0.05, "silence_duration_ms": 700},
                        },
                    })
                    updated = ws.receive_json()

        self.assertEqual(updated["type"], "transcription_session.updated")
        self.assertEqual(updated["session"]["sample_rate"], 24000)
        self.assertEqual(updated["session"]["input_audio_transcription"]["language"], "fr")
        self.assertEqual(updated["session"]["turn_detection"]["silence_duration_ms"], 700)

    def test_rejects_invalid_base64_audio(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({"type": "input_audio_buffer.append", "audio": "!!!not-base64!!!"})
                    error = ws.receive_json()

        self.assertEqual(error["type"], "error")

    def test_clear_buffer_acknowledged(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({"type": "input_audio_buffer.append", "audio": _b64(_pcm16_tone(0.3))})
                    ws.send_json({"type": "input_audio_buffer.clear"})
                    messages = [ws.receive_json() for _ in range(2)]

        self.assertIn("input_audio_buffer.cleared", [m["type"] for m in messages])

    def test_vad_detects_speech_and_emits_transcription(self):
        """Tone then silence must trigger speech_started/stopped and a transcript."""
        fake_result = {"text": "hello there", "language": "en", "segments": []}

        with patch("main.ensure_model"), patch("main.preload_models"), \
             patch("api.realtime_endpoints._transcribe_pcm", return_value=fake_result):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({"type": "input_audio_buffer.append", "audio": _b64(_pcm16_tone(1.0))})
                    ws.send_json({"type": "input_audio_buffer.append", "audio": _b64(_pcm16_silence(1.0))})

                    seen = []
                    for _ in range(6):
                        seen.append(ws.receive_json()["type"])
                        if seen[-1] == "conversation.item.input_audio_transcription.completed":
                            break

        self.assertIn("input_audio_buffer.speech_started", seen)
        self.assertIn("input_audio_buffer.speech_stopped", seen)
        self.assertIn("conversation.item.input_audio_transcription.delta", seen)
        self.assertIn("conversation.item.input_audio_transcription.completed", seen)

    def test_explicit_commit_produces_transcript(self):
        fake_result = {"text": "committed text", "language": "en", "segments": []}

        with patch("main.ensure_model"), patch("main.preload_models"), \
             patch("api.realtime_endpoints._transcribe_pcm", return_value=fake_result):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    # turn_detection=null disables VAD so commit is the only trigger.
                    ws.send_json({"type": "session.update", "session": {"turn_detection": None}})
                    ws.receive_json()
                    ws.send_json({"type": "input_audio_buffer.append", "audio": _b64(_pcm16_tone(1.0))})
                    ws.send_json({"type": "input_audio_buffer.commit"})

                    types, transcript = [], None
                    for _ in range(4):
                        msg = ws.receive_json()
                        types.append(msg["type"])
                        if msg["type"] == "conversation.item.input_audio_transcription.completed":
                            transcript = msg["transcript"]
                            break

        self.assertIn("input_audio_buffer.committed", types)
        self.assertEqual(transcript, "committed text")

    def test_commit_with_no_audio_is_ignored(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({"type": "input_audio_buffer.commit"})
                    ws.send_json({"type": "input_audio_buffer.clear"})
                    message = ws.receive_json()

        # No committed/transcript events for an empty buffer.
        self.assertEqual(message["type"], "input_audio_buffer.cleared")

    def test_unsupported_event_type_returns_error(self):
        with patch("main.ensure_model"), patch("main.preload_models"):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({"type": "response.create"})
                    error = ws.receive_json()

        self.assertEqual(error["type"], "error")


class VadUnitTests(unittest.TestCase):
    def test_detects_speech_then_silence(self):
        from utils.pcm_audio import EnergyVad

        vad = EnergyVad(sample_rate=16000, silence_duration_ms=300)
        self.assertIn("speech_started", vad.process(_pcm16_tone(0.5)))
        self.assertIn("speech_stopped", vad.process(_pcm16_silence(0.6)))

    def test_silence_alone_produces_no_events(self):
        from utils.pcm_audio import EnergyVad

        vad = EnergyVad(sample_rate=16000)
        self.assertEqual(vad.process(_pcm16_silence(1.0)), [])

    def test_wav_roundtrip_duration(self):
        import wave
        from utils.pcm_audio import pcm_duration_sec, write_wav

        pcm = _pcm16_tone(0.5)
        self.assertAlmostEqual(pcm_duration_sec(pcm, 16000), 0.5, places=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_wav(os.path.join(tmpdir, "a.wav"), pcm, 16000)
            with wave.open(path, "rb") as handle:
                self.assertEqual(handle.getframerate(), 16000)
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertEqual(handle.getnframes(), 8000)


class RealtimePreviewTests(unittest.TestCase):
    """input_audio_buffer.preview must be a non-destructive, preview-pool read."""

    def test_preview_emits_event_without_clearing_buffer(self):
        fake_result = {"text": "half a sent", "language": "en", "segments": []}

        with patch("main.ensure_model"), patch("main.preload_models"), \
             patch("api.realtime_endpoints._transcribe_pcm", return_value=fake_result) as transcribe:
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({"type": "session.update", "session": {"turn_detection": None}})
                    ws.receive_json()
                    ws.send_json({"type": "input_audio_buffer.append", "audio": _b64(_pcm16_tone(1.0))})
                    ws.send_json({"type": "input_audio_buffer.preview"})
                    preview = ws.receive_json()

                    # The buffer must survive the preview: a real commit still
                    # has audio to transcribe afterwards.
                    ws.send_json({"type": "input_audio_buffer.commit"})
                    committed = [ws.receive_json() for _ in range(3)]

        self.assertEqual(preview["type"], "conversation.item.input_audio_transcription.preview")
        self.assertEqual(preview["transcript"], "half a sent")
        self.assertEqual(preview["sequence"], 1)
        self.assertIn(
            "conversation.item.input_audio_transcription.completed",
            [m["type"] for m in committed],
        )

        preview_call, commit_call = transcribe.call_args_list[0], transcribe.call_args_list[-1]
        # positional: session_id, pcm, rate, language, label, scope, diarization,
        #             append_to_session, pool
        self.assertFalse(preview_call.args[7])
        self.assertEqual(preview_call.args[8], Pipeline.POOL_PREVIEW)
        self.assertTrue(commit_call.args[7])
        self.assertEqual(commit_call.args[8], Pipeline.POOL_FINAL)

    def test_preview_is_skipped_when_session_lock_is_busy(self):
        session = realtime_endpoints.RealtimeSession("sess", None)

        async def _run():
            async with session.lock:
                await realtime_endpoints._preview_utterance(object(), session)

        with patch("api.realtime_endpoints._transcribe_pcm") as transcribe:
            asyncio.run(_run())

        transcribe.assert_not_called()

    def test_commit_does_not_wait_for_an_in_flight_preview(self):
        """The session lock must be free while a preview decodes.

        An in-flight threadpool decode cannot be cancelled, so the only way a
        commit is not queued behind one is for the preview to release the lock
        before decoding.
        """
        session = realtime_endpoints.RealtimeSession("sess", None)
        session.buffer.append(_pcm16_tone(3.0))
        lock_free_during_decode = {}

        def _fake(*args, **kwargs):
            lock_free_during_decode["value"] = not session.lock.locked()
            return {"text": "mid", "language": "en", "segments": []}

        sent = []

        async def _send(ws, payload, send_lock=None):
            sent.append(payload)

        with patch("api.realtime_endpoints._transcribe_pcm", side_effect=_fake), \
             patch("api.realtime_endpoints._send", side_effect=_send):
            asyncio.run(realtime_endpoints._preview_utterance(object(), session))

        self.assertTrue(lock_free_during_decode["value"])
        self.assertFalse(session.lock.locked())
        self.assertFalse(session.preview_active)
        self.assertEqual([m["type"] for m in sent],
                         ["conversation.item.input_audio_transcription.preview"])

    def test_preview_is_skipped_while_another_preview_decodes(self):
        """preview_active guards overlap now that the lock is released early."""
        session = realtime_endpoints.RealtimeSession("sess", None)
        session.buffer.append(_pcm16_tone(3.0))
        session.preview_active = True

        with patch("api.realtime_endpoints._transcribe_pcm") as transcribe:
            asyncio.run(realtime_endpoints._preview_utterance(object(), session))

        transcribe.assert_not_called()

    def test_stale_preview_is_dropped_when_a_commit_lands_mid_decode(self):
        session = realtime_endpoints.RealtimeSession("sess", None)
        session.buffer.append(_pcm16_tone(3.0))

        def _fake(*args, **kwargs):
            # Simulate a real commit completing while this decode runs.
            session.utterance_index += 1
            return {"text": "stale", "language": "en", "segments": []}

        sent = []

        async def _send(ws, payload, send_lock=None):
            sent.append(payload)

        with patch("api.realtime_endpoints._transcribe_pcm", side_effect=_fake), \
             patch("api.realtime_endpoints._send", side_effect=_send):
            asyncio.run(realtime_endpoints._preview_utterance(object(), session))

        self.assertEqual(sent, [])
        self.assertFalse(session.preview_active)

    def test_preview_active_is_cleared_when_the_decode_raises(self):
        session = realtime_endpoints.RealtimeSession("sess", None)
        session.buffer.append(_pcm16_tone(3.0))

        with patch("api.realtime_endpoints._transcribe_pcm", side_effect=RuntimeError("boom")):
            asyncio.run(realtime_endpoints._preview_utterance(object(), session))

        self.assertFalse(session.preview_active)
        self.assertFalse(session.lock.locked())

    def test_commit_is_not_delayed_by_an_in_flight_preview_over_the_socket(self):
        """The receive loop must keep reading while a preview decodes.

        Releasing session.lock during the decode is not enough on its own: if
        the loop awaits _preview_utterance inline, a commit sent afterwards
        sits unread until the preview finishes. This drives the real socket so
        the loop itself is under test, not just the helper.
        """
        preview_started = threading.Event()
        release_preview = threading.Event()

        def _fake(session_id, pcm, sample_rate, language, label, scope,
                  diarization, append_to_session, pool):
            if pool == Pipeline.POOL_PREVIEW:
                preview_started.set()
                # Block until the commit has been fully served.
                release_preview.wait(timeout=10)
                return {"text": "partial", "language": "en", "segments": []}
            return {"text": "final text", "language": "en", "segments": []}

        with patch("main.ensure_model"), patch("main.preload_models"), \
             patch("api.realtime_endpoints._transcribe_pcm", side_effect=_fake):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({"type": "session.update", "session": {"turn_detection": None}})
                    ws.receive_json()
                    ws.send_json({"type": "input_audio_buffer.append", "audio": _b64(_pcm16_tone(1.0))})

                    ws.send_json({"type": "input_audio_buffer.preview"})
                    self.assertTrue(preview_started.wait(timeout=10),
                                    "preview decode never started")

                    # Preview is still blocked inside its decode. If the loop
                    # awaited it inline, this commit would not be read and the
                    # receive below would block until the timeout.
                    ws.send_json({"type": "input_audio_buffer.commit"})
                    events = [ws.receive_json() for _ in range(3)]
                    types = [e["type"] for e in events]

                    self.assertIn("input_audio_buffer.committed", types)
                    self.assertIn(
                        "conversation.item.input_audio_transcription.completed", types)
                    # No preview event may have arrived: it is still decoding.
                    self.assertNotIn(
                        "conversation.item.input_audio_transcription.preview", types)

                    release_preview.set()

    def test_pending_preview_is_cancelled_on_disconnect(self):
        async def _run():
            session = realtime_endpoints.RealtimeSession("sess", None)
            started = asyncio.Event()

            async def _slow():
                started.set()
                await asyncio.sleep(30)

            task = session.spawn(_slow())
            await started.wait()
            self.assertIn(task, session.background_tasks)

            await session.drain_background_tasks()
            self.assertTrue(task.cancelled())
            self.assertEqual(session.background_tasks, set())

        asyncio.run(_run())

    def test_drain_is_a_noop_without_background_tasks(self):
        session = realtime_endpoints.RealtimeSession("sess", None)
        asyncio.run(session.drain_background_tasks())
        self.assertEqual(session.background_tasks, set())

    def test_socket_writes_are_serialized_by_send_lock(self):
        """Concurrent senders must not interleave frames on the wire."""
        async def _run():
            session = realtime_endpoints.RealtimeSession("sess", None)
            order = []

            class FakeWs:
                async def send_text(self, text):
                    order.append(("start", text))
                    await asyncio.sleep(0)   # yield; a second sender may cut in
                    order.append(("end", text))

            ws = FakeWs()
            await asyncio.gather(
                realtime_endpoints._send(ws, {"n": 1}, send_lock=session.send_lock),
                realtime_endpoints._send(ws, {"n": 2}, send_lock=session.send_lock),
            )
            return order

        order = asyncio.run(_run())
        # Each write must complete before the next begins.
        self.assertEqual([phase for phase, _ in order],
                         ["start", "end", "start", "end"])
        self.assertEqual(order[0][1], order[1][1])
        self.assertEqual(order[2][1], order[3][1])

    def test_preview_window_is_bounded(self):
        """Only the trailing window is decoded, not the whole utterance."""
        captured = {}

        def _fake(session_id, pcm, *args, **kwargs):
            captured["len"] = len(pcm)
            return {"text": "", "language": "en", "segments": []}

        with patch("main.ensure_model"), patch("main.preload_models"), \
             patch("api.realtime_endpoints._transcribe_pcm", side_effect=_fake):
            with TestClient(main.app) as client:
                with client.websocket_connect("/v1/realtime?intent=transcription") as ws:
                    ws.receive_json()
                    ws.send_json({"type": "session.update", "session": {"turn_detection": None}})
                    ws.receive_json()
                    for _ in range(6):
                        ws.send_json({
                            "type": "input_audio_buffer.append",
                            "audio": _b64(_pcm16_tone(1.0)),
                        })
                    ws.send_json({"type": "input_audio_buffer.preview"})
                    ws.receive_json()

        window_bytes = int(realtime_endpoints.PREVIEW_MAX_WINDOW_SECONDS * 16000) * 2
        self.assertEqual(captured["len"], window_bytes)


class RealtimeLanguageGatingTests(unittest.TestCase):
    """The language hint is dropped only for English-only checkpoints."""

    def test_multilingual_model_keeps_language(self):
        with patch("api.realtime_endpoints.config.models.asr.name", "whisper-small"):
            self.assertEqual(
                realtime_endpoints._language_for_pool(Pipeline.POOL_FINAL, "fr"), "fr"
            )

    def test_english_only_model_drops_language(self):
        with patch("api.realtime_endpoints.config.models.asr.name", "distil-small.en"):
            self.assertIsNone(
                realtime_endpoints._language_for_pool(Pipeline.POOL_FINAL, "fr")
            )

    def test_preview_pool_uses_its_own_model_name(self):
        preview_cfg = SimpleNamespace(name="whisper-small")
        with patch("api.realtime_endpoints.config.models.asr.name", "distil-small.en"), \
             patch("api.realtime_endpoints.config.models.asr.preview", preview_cfg, create=True):
            self.assertEqual(
                realtime_endpoints._language_for_pool(Pipeline.POOL_PREVIEW, "fr"), "fr"
            )
            self.assertIsNone(
                realtime_endpoints._language_for_pool(Pipeline.POOL_FINAL, "fr")
            )


class TranscriptionsEndpointPoolTests(unittest.TestCase):
    """POST /v1/audio/transcriptions is always a final-pool, persisting call."""

    def _post(self, form=None, model_name="whisper-small"):
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = os.path.join(tmpdir, "clip.wav")
            with open(saved, "wb") as handle:
                handle.write(b"fake-audio")

            with patch("main.ensure_model"), patch("main.preload_models"), \
                 patch("api.openai_endpoints.save_audio_file", return_value=("clip.wav", saved)), \
                 patch("api.openai_endpoints.resolve_asr_device", return_value="CPU"), \
                 patch("api.openai_endpoints.Pipeline") as mock_pipeline_cls:
                mock_pipeline_cls.POOL_FINAL = Pipeline.POOL_FINAL
                mock_pipeline_cls.POOL_PREVIEW = Pipeline.POOL_PREVIEW
                instance = mock_pipeline_cls.return_value
                instance.session_id = "sess-1"
                instance.asr_model_name = model_name
                instance.transcribe.return_value = {
                    "text": "hi", "language": "en", "duration": 1.0, "segments": [],
                }
                with TestClient(main.app) as client:
                    response = client.post(
                        "/v1/audio/transcriptions",
                        data=form or {},
                        files={"file": ("clip.wav", b"fake-audio", "audio/wav")},
                    )
                return response, mock_pipeline_cls, instance

    def test_new_session_uses_final_pool(self):
        """Regression: the first call of a session must not land on the preview pool."""
        response, pipeline_cls, _ = self._post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(pipeline_cls.call_args.kwargs["pool"], Pipeline.POOL_FINAL)
        self.assertFalse(pipeline_cls.call_args.kwargs["append_to_session"])

    def test_multilingual_model_keeps_caller_language(self):
        _, _, instance = self._post(form={"language": "fr"}, model_name="whisper-small")

        self.assertEqual(instance.transcribe.call_args.kwargs["language"], "fr")

    def test_english_only_model_drops_caller_language(self):
        _, _, instance = self._post(form={"language": "fr"}, model_name="distil-small.en")

        self.assertIsNone(instance.transcribe.call_args.kwargs["language"])


if __name__ == "__main__":
    unittest.main()
