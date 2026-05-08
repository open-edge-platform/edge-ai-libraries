# API Use Cases, Examples, and Reference

## `GET /health`

Returns:

```json
{"status": "ok"}
```

## `GET /v1/audio/voices`

Returns the configured model metadata plus supported speakers and languages.

Example:

```bash
curl --noproxy '*' http://127.0.0.1:8011/v1/audio/voices
```

## `POST /v1/audio/speech`

JSON body fields:

- `model`: required field for OpenAI API compatibility; the value is ignored — the service always uses the model defined in `config.yaml`. Pass any string such as `"default"`.
- `input`: required text to synthesize
- `voice`: optional speaker name; defaults to the configured speaker
- `language`: optional language; defaults to the configured language
- `instructions`: optional speaking style guidance
- `response_format`: `wav` or `json`

If `response_format` is `wav`, the endpoint returns raw `audio/wav` and includes `X-Session-ID` in the response header. If it is `json`, the endpoint returns metadata plus a base64-encoded WAV payload.

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

Example — SpeechT5 (set `models.tts.name` to `microsoft/speecht5_tts` in `config.yaml`):

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

> SpeechT5 uses a single fixed speaker embedding; the `voice` and `language` fields are accepted but ignored.