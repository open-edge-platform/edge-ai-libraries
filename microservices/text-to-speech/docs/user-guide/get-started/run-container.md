# Run With Docker Compose

Use this path to run the service in a container using the prebuilt image
published on Docker Hub. The API is exposed on port `8011`.

To rebuild the image from source instead of pulling, see the
[Build From Source](./build-from-source.md) guide.

## Before You Start

- Edit `config.yaml` with the settings you want. The same file is used for both standalone and container runs. For configuration details, see the [Configuration Guide](./configuration.md).
- The Compose setup mounts `config.yaml`, `models/`, `storage/`, and the Hugging Face cache into the container.
- `/dev/dri` is passed through by default for host Intel iGPU access.
- The image reference is `${REGISTRY}/text-to-speech:${RELEASE_TAG}`, both read from `.env`. Defaults are `REGISTRY=intel` and the committed `RELEASE_TAG` pins the current release.

## Run the Container

### Pull And Start

From the `text-to-speech/` directory:

```bash
docker compose pull
docker compose up -d
```

`docker compose pull` fetches `intel/text-to-speech:${RELEASE_TAG}` from
Docker Hub. `docker compose up -d` starts the container without
rebuilding.

### Check Status

```bash
docker compose ps
curl --noproxy '*' http://127.0.0.1:8011/health
```

### Follow Logs

```bash
docker compose logs -f text-to-speech
```

### Restart

If you changed only `config.yaml`:

```bash
docker compose restart text-to-speech
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

- Container host port: `8011`
- The service loads `config.yaml` (bind-mounted from the host); the same file is used in standalone mode
- First startup can take longer because model download or conversion may happen during startup
- Linux iGPU access depends on the host exposing `/dev/dri` and having Intel/OpenVINO host GPU support installed
