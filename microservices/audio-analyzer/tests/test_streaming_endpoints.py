# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Tests for OpenAI-compatible SSE streaming and the realtime WebSocket API."""
import base64
import json
import math
import os
import struct
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


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


if __name__ == "__main__":
    unittest.main()
