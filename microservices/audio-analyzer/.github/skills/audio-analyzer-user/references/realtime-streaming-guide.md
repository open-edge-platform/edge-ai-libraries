<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Realtime Streaming Guide

Protocol, VAD tuning, and a runnable client for `WS /v1/realtime` — the
service's continuous, live audio transcription endpoint.

---

## Why This Endpoint Is Different

The HTTP transcription endpoints take a **finite upload** and chunk it by
file boundaries. `/v1/realtime` instead accepts an **open-ended** PCM audio
feed; the service decides where each transcribed utterance ends using
server-side voice activity detection (VAD) — not file boundaries. The
service never captures a local microphone itself (it is containerized and
has no reliable host audio device): the client owns capture and streaming,
the service owns transcription.

---

## Connecting

```
ws://<host>:8010/v1/realtime?intent=transcription[&session_id=<id>][&language=<hint>]
```

| Query param | Required | Description |
|-------------|----------|-------------|
| `intent` | No | Must be `transcription` (default) |
| `session_id` | No | Reuse to continue an existing session. Validated server-side — letters, digits, `-`, and `_` only, max 128 characters. An invalid value (e.g. containing `/`, `..`, or other path-unsafe characters) is rejected with an `error` event and the socket is closed (code `1008`); the service never joins an unvalidated value into its storage path. |
| `language` | No | Language hint passed to the ASR backend |

On connect, the server sends `transcription_session.created` describing the
negotiated audio format (PCM16, mono, 16 kHz by default).

---

## Audio Format Requirements

- **PCM16** (signed 16-bit little-endian), **mono**, **base64-encoded**.
- Default sample rate 16000 Hz; change with a `session.update` message
  before streaming audio.
- No resampling happens in the socket layer — downstream ffmpeg/Whisper
  handle it, so sending the wrong sample rate without updating the session
  will skew timing, not get silently fixed.
- Limits: 5 MB per `input_audio_buffer.append` message; any single
  utterance is force-committed at 120 seconds even without a VAD-detected
  pause.

---

## Client → Server Events

| Event | Payload | Purpose |
|-------|---------|---------|
| `session.update` | `{"session": {...}}` | Set `sample_rate`, `input_audio_transcription.language`, or `turn_detection` |
| `input_audio_buffer.append` | `{"audio": "<base64 pcm16>"}` | Push audio into the rolling buffer |
| `input_audio_buffer.commit` | — | Force-close the current utterance and transcribe it now |
| `input_audio_buffer.clear` | — | Discard buffered audio without transcribing |
| `session.close` | — | Flush the buffer and close the socket |

## Server → Client Events

| Event | Meaning |
|-------|---------|
| `transcription_session.created` / `.updated` | Current session configuration |
| `input_audio_buffer.speech_started` / `.speech_stopped` | Server VAD detected start/end of speech |
| `input_audio_buffer.committed` | An utterance was closed and is being transcribed |
| `input_audio_buffer.cleared` | Buffer discarded |
| `conversation.item.input_audio_transcription.delta` | Incremental transcript text for the current utterance |
| `conversation.item.input_audio_transcription.completed` | Final `transcript` for the utterance, plus `language`/`sentiment_summary` when available |
| `error` | `{"error": {"type": ..., "message": ...}}` |

---

## Turn Detection (VAD) Tuning

Default is energy-based server VAD:

```json
{"type": "session.update",
 "session": {"turn_detection": {"type": "server_vad",
                                "threshold": 0.02,
                                "silence_duration_ms": 500,
                                "prefix_padding_ms": 300}}}
```

`threshold` is **normalized RMS in 0..1** — it is not a neural VAD
probability. If `speech_started` never fires, the audio is quieter than the
threshold; lower it (e.g. `0.005`) for quiet sources. Raise it for noisy
environments to avoid spurious commits.

To disable VAD and control utterance boundaries yourself:

```json
{"type": "session.update", "session": {"turn_detection": null}}
```

then send `{"type": "input_audio_buffer.commit"}` whenever the client wants
a transcript.

---

## Runnable Client Pattern

```python
import asyncio, base64, json, websockets

SAMPLE_RATE = 16000

async def main():
    pcm = open("/tmp/audio.raw", "rb").read()       # raw PCM16, mono, 16kHz
    silence = b"\x00\x00" * int(SAMPLE_RATE * 1.2)   # triggers VAD end-of-speech

    url = "ws://127.0.0.1:8010/v1/realtime?intent=transcription"
    async with websockets.connect(url, max_size=None) as ws:
        print(json.loads(await ws.recv())["type"])   # transcription_session.created

        async def send():
            frame = int(SAMPLE_RATE * 0.1) * 2       # 100 ms frames
            for i in range(0, len(pcm), frame):
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm[i:i + frame]).decode(),
                }))
                await asyncio.sleep(0.005)
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(silence).decode(),
            }))

        asyncio.create_task(send())
        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == "conversation.item.input_audio_transcription.completed":
                print("TRANSCRIPT:", msg["transcript"])
                break

asyncio.run(main())
```

Expected event sequence:

```text
transcription_session.created
input_audio_buffer.speech_started
input_audio_buffer.speech_stopped
input_audio_buffer.committed
conversation.item.input_audio_transcription.delta
conversation.item.input_audio_transcription.completed
```

---

## Session Continuity Across a Live Connection

Because all committed utterances on one socket share a single session, the
session-level transcript accumulates across the entire connection the same
way it would across multiple HTTP uploads with the same `session_id`. Pass
`session_id` as a query param on reconnect to continue the same session
after a dropped connection — reuse the exact value the server assigned
(returned in `transcription_session.created`), since a hand-crafted id must
still pass the letters/digits/`-`/`_`, max-128-character validation.

Transcription is serialized per socket (results stay in order) and runs in a
thread pool so the event loop stays responsive to new `append` messages
while a previous utterance is still being transcribed.
