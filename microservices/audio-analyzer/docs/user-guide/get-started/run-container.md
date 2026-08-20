# Run With Docker Compose

Use this path to run the service in a container using the prebuilt image
published on Docker Hub. The API is exposed on port `8010`.

To rebuild the image from source instead of pulling, see the
[Build From Source](./build-from-source.md) guide.

## Before You Start

- Edit `config.yaml` with the settings you want. The same file is used for both standalone and container runs. For configuration details, see the [Configuration Guide](./configuration.md).
- The Compose setup bind-mounts `config.yaml` and stores model, chunk, storage, and Hugging Face cache data in named Docker volumes (`audio_analyzer_models`, `audio_analyzer_chunks`, `audio_analyzer_storage`, `audio_analyzer_cache`). Nothing is written into the source tree.
- `/dev/dri` is passed through by default for host Intel iGPU access.
- For Intel NPU acceleration, set `ACCEL_MOUNT_PATH` in your local `.env` (or export it before running Compose) to the host NPU device node. The host path is machine-specific; on some Meteor Lake systems it is `/dev/accel/accel0`.
- Compose maps the configurable host path `${ACCEL_MOUNT_PATH}` to the fixed container path `/dev/accel/accel0` expected by the OpenVINO NPU stack.
- Keep `ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so` in the container environment.
- CPU/GPU-only users do not need to configure an NPU path.

Example local `.env` entry for hosts that expose that node:

```bash
ACCEL_MOUNT_PATH=/dev/accel/accel0
```

Quick verification before `docker compose up`:

```bash
ls -l /dev/accel/
docker compose config
```

In resolved Compose output, confirm device mapping under `services.audio-analyzer.devices`:

- With `ACCEL_MOUNT_PATH` set:
   - `source: <your host NPU path>`
   - `target: /dev/accel/accel0`
- Without `ACCEL_MOUNT_PATH`:
   - `source: /dev/null`
   - `target: /dev/accel/accel0`
- The container runs as UID/GID `1000:1000` (baked into the image). The named volumes are initialized with that ownership, so no host UID/GID configuration is required.
- The image reference is `${REGISTRY}/audio-analyzer:${RELEASE_TAG}`, both read from `.env`. Defaults are `REGISTRY=intel` and the committed `RELEASE_TAG` pins the current release.

### Speaker Diarization Setup (Optional)

If you plan to enable speaker diarization by setting `models.asr.diarization: true` in `config.yaml`:

1. Create a [Hugging Face account](https://huggingface.co/settings/tokens) and generate a personal access token (free).
2. Accept the [Pyannote speaker-diarization model license](https://huggingface.co/pyannote/speaker-diarization-community-1)
   on Hugging Face. Visit the link and click the gate acceptance button. This is a one-time requirement per account.
3. Set your Hugging Face token in the `.env` file:
   ```bash
   HF_TOKEN=hf_your_token_here
   ```
4. Restart the container:
   ```bash
   docker compose up -d
   ```

Without a valid `HF_TOKEN` and gate acceptance, speaker diarization will not initialize. The service
continues running, logs a warning, and disables diarization for that session.
If diarization is disabled in `config.yaml`, `HF_TOKEN` is not required.

### MinIO (External Object Storage)

MinIO is an **external dependency** for the `POST /transcriptions` endpoint's
object-storage source/sink mode: it is not defined as a service in
`docker-compose.yml`, and Audio Analyzer does not start, bundle, or manage
it. When a caller supplies `minio_bucket`/`video_id`/`video_name` instead of
uploading a file directly, Audio Analyzer downloads that one source
audio/video object from the bucket, transcribes it, and uploads the
resulting transcript back into the same bucket — no other endpoint touches
MinIO, and no audio chunks are stored in MinIO (chunking is an internal,
local processing step). Run MinIO as a separate container (or use an
existing MinIO deployment) and provide its endpoint/credentials to Audio
Analyzer through configuration. For full details on the config keys and env
vars, see the
[MinIO section of the Configuration Guide](./configuration.md#minio-external-dependency).

`docker-compose.yml` only forwards the specific environment variables it
lists under `services.audio-analyzer.environment`; values placed in `.env`
are not automatically injected into the container unless referenced there.
To supply MinIO settings to the running container, either:

- Edit the bind-mounted `config.yaml` directly (`minio.endpoint`,
  `minio.access_key`, `minio.secret_key`, `minio.secure`) and
  `docker compose restart audio-analyzer`; or
- Add the `AUDIO_ANALYZER__MINIO__*` variables under
  `services.audio-analyzer.environment` in `docker-compose.yml` so Compose
  passes them into the container.

Example: run MinIO as its own container on the same Docker network Audio
Analyzer uses, then supply its connection details via `config.yaml`:

```bash
docker run -d --name minio-server --network <your-network> \
  -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=<your-access-key> \
  -e MINIO_ROOT_PASSWORD=<your-secret-key> \
  minio/minio server /data --console-address ":9001"
```

```yaml
# config.yaml
minio:
  endpoint: "minio-server:9000"
  access_key: "<your-access-key>"
  secret_key: "<your-secret-key>"
  secure: false
```

Verification steps:

```bash
# 1. MinIO is running
docker ps --filter name=minio-server
curl --noproxy '*' http://127.0.0.1:9000/minio/health/live

# 2. MinIO configuration was passed to Audio Analyzer
#    (config.yaml is bind-mounted; inspect the mounted file, or if using the
#    environment-variable approach, check the container's environment)
docker compose exec audio-analyzer cat /app/audio_analyzer/config.yaml | grep -A4 '^minio:'
docker compose exec audio-analyzer env | grep AUDIO_ANALYZER__MINIO__

# 3. Audio Analyzer resolved the MinIO endpoint
docker compose logs audio-analyzer | grep -i minio

# 4. Audio Analyzer can reach MinIO's health endpoint from inside the container
docker compose exec audio-analyzer python3 -c \
  "import urllib.request; urllib.request.urlopen('http://minio-server:9000/minio/health/live', timeout=5).read()"
```

If step 4 fails but MinIO is otherwise reachable, check whether
`http_proxy`/`https_proxy` are set in the container environment and whether
`no_proxy`/`NO_PROXY` includes the MinIO hostname — a proxy can block direct
container-to-container requests even when the network path itself is fine.
This is a proxy/environment configuration matter, not an Audio Analyzer or
MinIO defect.

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

For OpenVINO + NPU, also verify container/runtime visibility:

```bash
docker compose exec audio-analyzer ls -l /dev/accel/
docker compose exec audio-analyzer python3 -c "import openvino as ov; print([str(d).upper() for d in ov.Core().available_devices])"
```

The second command must include `NPU`.

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
