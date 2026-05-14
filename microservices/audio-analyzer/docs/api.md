# API Use Cases, Examples, and Reference

## `GET /health`

Returns:

```json
{"status": "ok"}
```

## `GET /devices`

Returns detected ALSA capture devices in `hw:<card>,<device>` format.

## `POST /v1/audio/transcriptions`

Form fields:

- `file`: required audio upload
- `model`: optional, accepted value is `whisper-1`
- `session_id`: optional, reuse to continue an existing session
- `language`: optional language hint
- `prompt`: accepted but currently ignored
- `response_format`: `json`, `text`, `verbose_json`, `srt`, `vtt`
- `temperature`: optional decoding temperature

The service returns `X-Session-ID` in the response header.

Example:

```bash
curl --noproxy '*' \
  -F file=@question_store_hours.wav \
  -F response_format=verbose_json \
  http://127.0.0.1:8010/v1/audio/transcriptions
```

If `session_id` is omitted, the service creates one and returns it in `X-Session-ID`. Reusing that value with another upload continues the same session and appends transcript state.

## `POST /v1/audio/transcriptions/stream`

Form fields:

- `file`: required audio upload
- `session_id`: optional, reuse to continue an existing session
- `language`: optional language hint
- `temperature`: optional decoding temperature

Returns NDJSON events with:

- `transcription.chunk`
- `transcription.completed`

Example:

```bash
curl --noproxy '*' \
  -F file=@question_store_hours.wav \
  http://127.0.0.1:8010/v1/audio/transcriptions/stream
```