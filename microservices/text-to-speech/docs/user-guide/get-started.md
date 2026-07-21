# Get Started

This page guides you through the fastest path to a running Text To Speech microservice.
The recommended deployment uses Docker Compose. Alternative deployment options are available in the [How-to Guides](./how-to-guides.md) section.

## Before You Begin

- Confirm that your machine meets the
  [System Requirements](./get-started/system-requirements.md).
- Review the [Configuration Guide](./get-started/configuration.md) if you plan to change
  models, runtimes, devices, or precision.

## Deploy with Docker

The container image exposes the API on host port `8011` and mounts shared
folders for models, storage, and the Hugging Face cache.

```bash
docker compose up -d --build
```

If you hit permission errors on `models/`, `storage/`, or
`.cache/huggingface/`, see
[Troubleshooting](./troubleshooting.md#permission-errors-on-mounted-folders).

For the full step-by-step guide, see [Run with Docker Compose](./get-started/run-container.md).

## Verify

Once the service is running:

```bash
curl --noproxy '*' http://127.0.0.1:8011/health
```

Expected response:

```json
{"status": "ok"}
```

## Try It Out

Once the service responds to the health check, send a speech synthesis request:

```bash
curl --noproxy '*' -sS \
  -o speech.wav \
  -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8011/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "default",
    "input": "The kiosk is ready for your next request.",
    "response_format": "wav"
  }'
```

Expected output:

```
200
```

The synthesized audio is saved to `speech.wav` in the current directory. Play
it with any WAV-capable player (`aplay speech.wav` on Linux, or open it in a
media player).

To list available voices and confirm the active model:

```bash
curl --noproxy '*' http://127.0.0.1:8011/v1/audio/voices
```

Expected output (example with the default SpeechT5 model):

```json
{
  "model": "microsoft/speecht5_tts",
  "runtime": "openvino",
  "speakers": ["default"],
  "languages": ["English"]
}
```

> **Note:** First startup may take longer than usual because the model is
> downloaded and converted during initialization. Subsequent starts are faster.

## Next Steps

- [API Reference](./api-reference.md) for full endpoint details, Qwen TTS examples, and session persistence
- [Configuration Guide](./get-started/configuration.md) to customize the model, runtime, and device
- [Troubleshooting](./troubleshooting.md) for common startup issues

### Other Deployment Options

- [Run on the Host](./how-to-guides/run-standalone.md) — run directly with Python, without Docker
- [Build from Source](./how-to-guides/build-from-source.md) — build the Docker image from source code

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements.md
./get-started/configuration.md
./get-started/run-container.md

:::
hide_directive-->
