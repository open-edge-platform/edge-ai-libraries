# Run Without Docker

Use this path when you want to run the service directly with Python on the host.

## System Packages

Install the runtime system dependencies first:

```bash
sudo apt-get update
sudo apt-get install -y libsndfile1
```

These host packages are required for standalone execution on the machine.

## Python Setup

From the `text-to-speech/` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Config

- Edit `config.yaml`. For configuration details, see [configuration.md](configuration.md).
- The same `config.yaml` is used for both standalone and container runs.
- Use `TEXT_TO_SPEECH__...` environment variables only for targeted overrides.
- For Linux Intel iGPU usage, first install the required Intel/OpenVINO host runtime on the machine, then set the OpenVINO device field to `GPU` in config.

## Start

```bash
source .venv/bin/activate
python main.py
```

Default bind address:

- host: `127.0.0.1`
- port: `8011`

To change host or port:

```bash
TEXT_TO_SPEECH_SERVER_HOST=0.0.0.0 TEXT_TO_SPEECH_SERVER_PORT=8011 python main.py
```

Equivalent `uvicorn` command:

```bash
uvicorn main:app --host 127.0.0.1 --port 8011
```

## Verify

```bash
curl --noproxy '*' http://127.0.0.1:8011/health
```

## API Use Cases and Examples

For API use cases, request examples, and endpoint details, see
[api-reference.md](api-reference.md).

## Notes

- The service ensures model assets on startup and preloads configured models
- First startup can take longer because models may be downloaded or converted
- Runtime outputs are stored under `storage/<session_id>/`
- Host-side Linux iGPU/OpenVINO GPU is the validated GPU path for this setup