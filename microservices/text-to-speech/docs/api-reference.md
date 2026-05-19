# API Reference

Base URL: `http://127.0.0.1:8011` (default).

All endpoints return JSON unless noted. The speech endpoint also sets the
`X-Session-ID` response header on `wav` responses; clients that want to
correlate uploads with persisted storage should read it.

## `GET /health`

Liveness probe.

Response:

```json
{"status": "ok"}
```

## `GET /v1/audio/voices`

Returns the configured model metadata, supported speakers, and the
currently supported language list.

Example:

```bash
curl --noproxy '*' http://127.0.0.1:8011/v1/audio/voices
```

## `POST /v1/audio/speech`

Synthesize speech from text.

JSON body fields:

| Field             | Required | Description                                                                                              |
| ----------------- | -------- | -------------------------------------------------------------------------------------------------------- |
| `model`           | Yes      | Required for OpenAI API compatibility; value is ignored. The service always uses the configured model.   |
| `input`           | Yes      | Text to synthesize.                                                                                      |
| `voice`           | No       | Speaker name; defaults to the configured speaker.                                                        |
| `language`        | No       | Only `English` is currently accepted.                                                                    |
| `instructions`    | No       | Optional speaking style guidance (where supported by the model).                                         |
| `response_format` | No       | `wav` (raw `audio/wav`) or `json` (metadata + base64-encoded WAV).                                       |

Example — SpeechT5 (set `models.tts.name` to `microsoft/speecht5_tts` in
`config.yaml`):

```bash
curl --noproxy '*' \
  -X POST http://127.0.0.1:8011/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "default",
    "input": "The kiosk is ready for your next request.",
    "response_format": "wav"
  }' \
  --output speech.wav
```

> SpeechT5 uses a single fixed speaker embedding; the `voice` and
> `language` fields are accepted but ignored.

Example — Qwen TTS (set `models.tts.name` to a Qwen model in `config.yaml`):

```bash
curl --noproxy '*' \
  -X POST http://127.0.0.1:8011/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "default",
    "input": "The kiosk is ready for your next request.",
    "voice": "Ryan",
    "language": "English",
    "instructions": "Speak clearly and warmly.",
    "response_format": "wav"
  }' \
  --output speech.wav
```

> The service currently supports English only. Requests that pass any
> other language return `400`.

## Sessions

When `pipeline.persist_outputs` is enabled, each `wav` response is
associated with a `session_id` returned in the `X-Session-ID` header. The
corresponding WAV and metadata are written under
`storage/<session_id>/`.

## Related

- Configuration of model, runtime, and device:
  [configuration.md](configuration.md)
