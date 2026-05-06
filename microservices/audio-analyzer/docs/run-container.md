# Run With Docker Compose

Use this path when you want the service to run in a container and expose the API on port `8000`.

## Before You Start

- Edit `config.container.yaml` with the settings you want. For configuration details and override behavior, see [configuration.md](configuration.md).
- The Compose setup mounts `config.container.yaml`, `models/`, `chunks/`, `storage/`, and Hugging Face cache into the container.

## Start

From the `audio_analyzer/` directory:

```bash
docker compose up -d --build
```

## Check Status

```bash
docker compose ps
curl --noproxy '*' http://127.0.0.1:8000/health
```

For endpoint details and request examples, see [api.md](api.md).

## Follow Logs

```bash
docker compose logs -f audio-analyzer
```

## Restart

If you changed only `config.container.yaml`:

```bash
docker compose restart audio-analyzer
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

- Container host port: `8000`
- The service loads `config.container.yaml` through `AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS`
- First startup can take longer because model download or export may happen during startup
- If you need host microphone access, uncomment the `/dev/snd` device mapping in `docker-compose.yml`
- Linux iGPU/OpenVINO GPU is not enabled by default in this Compose setup; the validated GPU path was host-side standalone execution
- On a new machine, installing Intel/OpenVINO host GPU support is a separate prerequisite from Python dependency installation
