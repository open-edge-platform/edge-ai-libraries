# Run With Docker Compose

Use this path to run the service in a container using the prebuilt image
published on Docker Hub. The API is exposed on port `8010`.

To rebuild the image from source instead of pulling, see the
[Build From Source](./build-from-source.md) guide.

## Before You Start

- Edit `config.yaml` with the settings you want. The same file is used for both standalone and container runs. For configuration details, see the [Configuration Guide](./configuration.md).
- The Compose setup bind-mounts `config.yaml` and stores model, chunk, storage, and Hugging Face cache data in named Docker volumes (`audio_analyzer_models`, `audio_analyzer_chunks`, `audio_analyzer_storage`, `audio_analyzer_cache`). Nothing is written into the source tree.
- `/dev/dri` is passed through by default for host Intel iGPU access.
- The container runs as UID/GID `1000:1000` (baked into the image). The named volumes are initialized with that ownership, so no host UID/GID configuration is required.
- The image reference is `${REGISTRY}/audio-analyzer:${RELEASE_TAG}`, both read from `.env`. Defaults are `REGISTRY=intel` and the committed `RELEASE_TAG` pins the current release.

## Run the Container

### Pull And Start

From the `audio-analyzer/` directory:

```bash
docker compose pull
docker compose up -d
```

`docker compose pull` fetches `intel/audio-analyzer:${RELEASE_TAG}` from
Docker Hub. `docker compose up -d` starts the container without
rebuilding.

### Check Status

```bash
docker compose ps
curl --noproxy '*' http://127.0.0.1:8010/health
```

### Follow Logs

```bash
docker compose logs -f audio-analyzer
```

### Restart

If you changed only `config.yaml`:

```bash
docker compose restart audio-analyzer
```

To pull a newer release tag, edit `RELEASE_TAG` in `.env`, then:

```bash
docker compose pull
docker compose up -d
```

For a clean restart:

```bash
docker compose down
docker compose up -d
```

### Stop

```bash
docker compose down
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see the [API Reference](../api-reference.md).

## Notes

- Container host port: `8010`
- The service loads `config.yaml` (bind-mounted from the host); the same file is used in standalone mode
- Model, chunk, storage, and Hugging Face cache data live in named Docker volumes managed by Compose; inspect them with `docker volume ls` and reset them with `docker volume rm` if needed
- First startup can take longer because model download or export may happen during startup
- If you need host microphone access, uncomment the `/dev/snd` device mapping in `docker-compose.yml`
- Linux iGPU access depends on the host exposing `/dev/dri` and having Intel/OpenVINO host GPU support installed
