# Run With Docker Compose

Use this path when you want the service to run in a container and expose the API on port `8011`.

## Before You Start

- Edit `config.yaml` with the settings you want. The same file is used for both standalone and container runs. For configuration details, see the [Configuration Guide](./configuration.md).
- The Compose setup mounts `config.yaml`, `models/`, `storage/`, and the Hugging Face cache into the container.
- `/dev/dri` is passed through by default for host Intel iGPU access.

## Running the Service

### Start

From the `text-to-speech/` directory:

```bash
docker compose up -d --build
```

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

If you changed code or dependencies:

```bash
docker compose up -d --build
```

For a clean restart:

```bash
docker compose down
docker compose up -d --build
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
- On a new machine, Intel/OpenVINO host GPU support is still a separate prerequisite from Python dependency installation
