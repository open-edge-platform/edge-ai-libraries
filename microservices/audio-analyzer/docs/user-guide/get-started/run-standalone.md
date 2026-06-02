# Run On the Host

Use this path when you want to run the service directly with Python on the host.

## Prerequisites

### System Packages

Install the runtime system dependencies first:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg alsa-utils libsndfile1
```

These host packages are required for standalone execution on the machine.

### Python Setup

From the `audio_analyzer/` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Config

- Edit `config.yaml`. For configuration details, see the [Configuration Guide](./configuration.md).
- The same `config.yaml` is used for both standalone and container runs.
- Use `AUDIO_ANALYZER__...` environment variables only for targeted overrides.
- For Linux Intel iGPU usage, first install the required Intel/OpenVINO host runtime on the machine, then set the OpenVINO device fields to `GPU` in config.

## Running the Service

### Start

```bash
source .venv/bin/activate
python main.py
```

Default bind address:

- host: `127.0.0.1`
- port: `8010`

To change host or port:

```bash
AUDIO_ANALYZER_SERVER_HOST=0.0.0.0 AUDIO_ANALYZER_SERVER_PORT=8010 python main.py
```

Equivalent `uvicorn` command:

```bash
uvicorn main:app --host 127.0.0.1 --port 8010
```

### Verify

```bash
curl --noproxy '*' http://127.0.0.1:8010/health
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see the [API Reference](../api-reference.md).

## Notes

- The service ensures model assets on startup and preloads configured models
- First startup can take longer because models may be downloaded or exported
- Runtime session files are stored under `storage/<session_id>/`
- Host-side Linux iGPU/OpenVINO GPU was the validated GPU path for this setup
