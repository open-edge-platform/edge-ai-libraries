# Run Without Docker

Use this path when you want to run the service directly with Python on the host.

## System Packages

Install the runtime system dependencies first:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg alsa-utils libsndfile1
```

These host packages are required for standalone execution on the machine.

## Python Setup

From the `audio_analyzer/` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Config

- Start from `config.yaml`. For configuration details and override behavior, see [configuration.md](configuration.md).
- Use `AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS` if you want one or more override YAML files
- Use `AUDIO_ANALYZER__...` environment variables only for targeted overrides
- For Linux Intel iGPU usage, first install the required Intel/OpenVINO host runtime on the machine, then set the OpenVINO device fields to `GPU` in config.

## Start

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

If your Linux iGPU setup provides an Intel oneAPI environment script, source it before starting the service:

```bash
source /opt/intel/oneapi/setvars.sh
python main.py
```

Equivalent `uvicorn` command:

```bash
uvicorn main:app --host 127.0.0.1 --port 8010
```

## Verify

```bash
curl --noproxy '*' http://127.0.0.1:8010/health
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see [api.md](api.md).

## Notes

- The service ensures model assets on startup and preloads configured models
- First startup can take longer because models may be downloaded or exported
- Runtime session files are stored under `storage/<session_id>/`
- Host-side Linux iGPU/OpenVINO GPU was the validated GPU path for this setup
- `/opt/intel/oneapi/setvars.sh` is not available on a default Ubuntu install; it appears only after the relevant Intel host stack is installed