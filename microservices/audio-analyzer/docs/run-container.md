# Run With Docker Compose

Use this path to run the service in a container using the prebuilt image
published on Docker Hub. The API is exposed on port `8010`.

To rebuild the image from source instead of pulling, see
[build-from-source.md](build-from-source.md).

## Before You Start

- Edit `config.yaml` with the settings you want. The same file is used for both standalone and container runs. For configuration details, see [configuration.md](configuration.md).
- The Compose setup mounts `config.yaml`, `models/`, `chunks/`, `storage/`, and the Hugging Face cache into the container.
- The repository includes placeholder files so fresh clones already contain those mount roots. If you remove any of those directories, recreate them as your user before starting Compose or Docker may recreate the missing host paths as `root`.
- `/dev/dri` is passed through by default for host Intel iGPU access.
- The image defaults to UID/GID `1000:1000`, and Compose also runs the container as `1000:1000` unless you override `LOCAL_UID` and `LOCAL_GID`. If your host user is different, see [troubleshooting.md](troubleshooting.md#permission-errors-on-mounted-folders) before starting.
- The image reference is `${REGISTRY}/audio-analyzer:${RELEASE_TAG}`, both read from `.env`. Defaults are `REGISTRY=intel` and the committed `RELEASE_TAG` pins the current release.

## Pull And Start

From the `audio-analyzer/` directory:

```bash
docker compose pull
docker compose up -d
```

`docker compose pull` fetches `intel/audio-analyzer:${RELEASE_TAG}` from
Docker Hub. `docker compose up -d` starts the container without
rebuilding.

## Check Status

```bash
docker compose ps
curl --noproxy '*' http://127.0.0.1:8010/health
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see [api-reference.md](api-reference.md).

## Follow Logs

```bash
docker compose logs -f audio-analyzer
```

## Restart

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

## Stop

```bash
docker compose down
```

## Notes

- Container host port: `8010`
- The service loads `config.yaml` (bind-mounted from the host); the same file is used in standalone mode
- The container writes shared files as the user it runs as (default `1000:1000`), so `models/`, `chunks/`, `storage/`, and `.cache/huggingface/` should remain usable from standalone host runs when host UID/GID match
- If a bind-mount source path is missing on the host, Docker may create it as `root` before the service starts; pre-create the directories if you cleaned them out
- First startup can take longer because model download or export may happen during startup
- If you need host microphone access, uncomment the `/dev/snd` device mapping in `docker-compose.yml`
- Linux iGPU access depends on the host exposing `/dev/dri` and having Intel/OpenVINO host GPU support installed
