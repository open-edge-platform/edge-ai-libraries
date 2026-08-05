# Get Started

This page is the entry point for running the Audio Analyzer microservice.
Pick one of the two deployment paths and follow the linked guide.

## Application Overview

The Audio Analyzer microservice provides automatic speech recognition (ASR) and optional speaker diarization.
It captures and transcribes audio, optionally identifying different speakers in the same audio chunk.
Optional sentiment analysis per chunk complements the transcription output.

If you enable speaker diarization in `config.yaml` (`models.asr.diarization: true`), you must provide a
Hugging Face access token (`HF_TOKEN`) and accept the Pyannote speaker-diarization model license on
Hugging Face if you want diarization to initialize successfully. If diarization setup is incomplete,
the service continues running and logs a warning while disabling diarization for that session.

## Before You Begin

- Confirm that your machine meets the
  [System Requirements](./get-started/system-requirements.md).
- Review the [Configuration Guide](./get-started/configuration.md) if you plan to change
  models, devices, or chunking behavior.

## Choose Deployment Path

<!--hide_directive::::{tab-set}
:::{tab-item}hide_directive--> **Run in Docker (Recommended)**
<!--hide_directive:sync: Docker hide_directive-->

The container image exposes the API on host port `8010` and mounts shared
folders for models, chunks, storage, and the Hugging Face cache.
Fresh clones include placeholder directories for these mount roots. If you
delete them and then start Compose, Docker may recreate the missing host
paths as `root` before the container starts.

See [Run with Docker Compose](./get-started/run-container.md) for the full step-by-step guide.

Quick start:

```bash
docker compose up -d --build
curl --noproxy '*' http://127.0.0.1:8010/health
```

If you hit permission errors on `models/`, `chunks/`, `storage/`, or
`.cache/huggingface/`, see
[Troubleshooting](./troubleshooting.md#permission-errors-on-mounted-folders).

<!--hide_directive:::
:::{tab-item}hide_directive--> **Run on the Host**
<!--hide_directive:sync: Host hide_directive-->

Run the service directly with Python. This path is useful for development or
when you do not want to use Docker.

See [Run on the Host](./get-started/run-standalone.md) for the full step-by-step guide.

Quick start:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
<!--hide_directive:::
::::hide_directive-->

## Verify

Once the service is running:

```bash
curl --noproxy '*' http://127.0.0.1:8010/health
```

Expected response:

```json
{"status": "ok"}
```

### Verify batch transcription

Transcribe a file and get a single JSON response:

```bash
curl --noproxy '*' -X POST http://127.0.0.1:8010/v1/audio/transcriptions \
  -F file=@tests/philosophy_10_russell_128kb.mp3
```

Expected: a JSON body containing a `"text"` field, plus an `X-Session-ID`
response header.

### Verify OpenAI-compatible streaming (SSE)

Add `stream=true` to receive incremental Server-Sent Events instead of
waiting for the whole file. Use `-N` so curl does not buffer the stream:

```bash
curl --noproxy '*' -N -X POST http://127.0.0.1:8010/v1/audio/transcriptions \
  -F file=@tests/philosophy_10_russell_128kb.mp3 \
  -F stream=true
```

Expected: a sequence of `transcript.text.delta` frames as each chunk is
transcribed, one final `transcript.text.done` frame with the full text, then
the `[DONE]` sentinel:

```text
data: {"type": "transcript.text.delta", "delta": "Chapter X of Philosophy by Bertrand Russell..."}

data: {"type": "transcript.text.delta", "delta": "The electron, which has been moving in one orbit..."}

data: {"type": "transcript.text.done", "text": "Chapter X of Philosophy by Bertrand Russell...", "language": "en", "duration": 612.4}

data: [DONE]
```

Because this matches OpenAI's documented event shape, official OpenAI SDKs
work against this endpoint — point the client's `base_url` at this service:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8010/v1", api_key="not-used")

with open("tests/philosophy_10_russell_128kb.mp3", "rb") as audio:
    stream = client.audio.transcriptions.create(
        model="whisper-1", file=audio, response_format="json", stream=True,
    )
    for event in stream:
        print(event)
```

> `stream=true` requires `response_format` to be `json` or `verbose_json`;
> `srt`, `vtt`, and `text` return HTTP 400.

### Verify continuous audio streaming (WebSocket)

`WS /v1/realtime?intent=transcription` accepts a *live, continuous* audio
feed. Clients push PCM16 frames and receive transcripts as each utterance
completes — server-side voice activity detection (VAD) decides where
utterances end.

Install a WebSocket client, decode some audio to raw PCM16, and stream it:

```bash
pip install websockets

# Decode 18s of audio to raw PCM16, mono, 16 kHz
ffmpeg -v error -i tests/philosophy_10_russell_128kb.mp3 -t 18 \
  -f s16le -ar 16000 -ac 1 /tmp/audio.raw
```

```python
import asyncio, base64, json, websockets

SAMPLE_RATE = 16000

async def main():
    pcm = open("/tmp/audio.raw", "rb").read()
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
            print("EVENT:", msg["type"])
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
TRANSCRIPT: Chapter X of Philosophy by Bertrand Russell...
```

If you never see `speech_started`, the audio is quieter than the VAD
threshold — lower it with a `session.update` message:

```json
{"type": "session.update",
 "session": {"turn_detection": {"threshold": 0.005, "silence_duration_ms": 700}}}
```

To disable VAD entirely and control utterance boundaries yourself, send
`"turn_detection": null` and then `{"type": "input_audio_buffer.commit"}`
whenever you want a transcript.

See the [API Reference](./api-reference.md#ws-v1realtime) for the full event
list and configuration options.

### Verify VSS-compatible endpoints

Video Search & Summarization (VSS) calls this service under an `/api/v1`
prefix:

```bash
curl --noproxy '*' http://127.0.0.1:8010/api/v1/models
```

Expected: a JSON body with `models` and `default_model`. The same routes are
also served unprefixed (`/models`, `/transcriptions`) for local use.

### Run the automated tests

```bash
pip install pytest httpx
pytest tests/test_streaming_endpoints.py tests/test_vss_endpoints.py -v
```

These cover the SSE event sequence, the realtime WebSocket handshake, VAD
behavior, and the VSS contract, and require no model weights or GPU.

## Next Steps

- [API Reference](./api-reference.md) for endpoint details and examples
- [Configuration Guide](./get-started/configuration.md) to customize models and devices
- [Troubleshooting](./troubleshooting.md) for common startup issues

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements.md
./get-started/configuration.md
./get-started/build-from-source.md
./get-started/run-container.md
./get-started/run-standalone.md

:::
hide_directive-->
