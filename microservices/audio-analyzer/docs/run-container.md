# Run With Docker Compose

Use this path when you want the service to run in a container and expose the API on port `8010`.

## Before You Start

- Edit `config.container.yaml` with the settings you want. For configuration details and override behavior, see [configuration.md](configuration.md).
- The Compose setup mounts `config.container.yaml`, `models/`, `chunks/`, `storage/`, and Hugging Face cache into the container.
- `/dev/dri` is passed through by default for host Intel iGPU access.
- The image defaults to UID/GID `1000:1000`, and Compose also runs the container as `1000:1000` unless you override `LOCAL_UID` and `LOCAL_GID`. If your host user is different, see [troubleshooting.md](troubleshooting.md#permission-errors-on-mounted-folders) before starting.

## Start

From the `audio_analyzer/` directory:

```bash
docker compose up -d --build
```

## Check Status

```bash
docker compose ps
curl --noproxy '*' http://127.0.0.1:8010/health
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see [api.md](api.md).

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

- Container host port: `8010`
- The service loads `config.container.yaml` through `AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS`
- The container writes shared files as the user it runs as (default `1000:1000`), so `models/`, `chunks/`, `storage/`, and `.cache/huggingface/` should remain usable from standalone host runs when host UID/GID match
- Direct image runs inherit the same non-root default unless you pass a different `--user`
- First startup can take longer because model download or export may happen during startup
- If you need host microphone access, uncomment the `/dev/snd` device mapping in `docker-compose.yml`
- Linux iGPU access now depends on the host exposing `/dev/dri` and having Intel/OpenVINO host GPU support installed
- On a new machine, Intel/OpenVINO host GPU support is still a separate prerequisite from Python dependency installation
