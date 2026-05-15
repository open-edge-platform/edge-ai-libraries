# Run With Docker Compose

Use this path when you want the service to run in a container and expose the API on port `8011`.

## Before You Start

- Edit `config.container.yaml` with the settings you want. For configuration details and override behavior, see [configuration.md](configuration.md).
- The Compose setup mounts `config.container.yaml`, `models/`, `storage/`, and Hugging Face cache into the container.
- `/dev/dri` is passed through by default for host Intel iGPU access.

## Start

From the `text-to-speech/` directory:

```bash
docker compose up -d --build
```

## Check Status

```bash
docker compose ps
curl --noproxy '*' http://127.0.0.1:8011/health
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see [api.md](api.md).

## Follow Logs

```bash
docker compose logs -f text-to-speech
```

## Restart

If you changed only `config.container.yaml`:

```bash
docker compose restart text-to-speech
```

If you changed code or dependencies:

```bash
docker compose up -d --build
```

For a clean restart:

```bash
docker compose down
docker compose up -d --build
```

## Stop

```bash
docker compose down
```

## Notes

- Container host port: `8011`
- The service loads `config.container.yaml` through `TEXT_TO_SPEECH_CONFIG_OVERRIDE_PATHS`
- First startup can take longer because model download or conversion may happen during startup
- Linux iGPU access depends on the host exposing `/dev/dri` and having Intel/OpenVINO host GPU support installed
- On a new machine, Intel/OpenVINO host GPU support is still a separate prerequisite from Python dependency installation