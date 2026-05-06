# Configuration

## Load Order

The service loads configuration in this order:

1. `config.yaml`
2. Files listed in `AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS`
3. Environment variables with the `AUDIO_ANALYZER__...` prefix

This applies to both Docker and standalone runs.

## Config Files

- `config.yaml`: base defaults for local or general use
- `config.container.yaml`: preferred container deployment config

For container deployments, edit `config.container.yaml` directly. For direct local runs, start from `config.yaml` and override only what you need.

## Environment Variables

- `AUDIO_ANALYZER_CONFIG_PATH`: alternate base config file
- `AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS`: comma-separated YAML override files
- `AUDIO_ANALYZER_ENV_FILE`: optional dotenv file to preload before config parsing
- `AUDIO_ANALYZER_SERVER_HOST`: host used by `python main.py`
- `AUDIO_ANALYZER_SERVER_PORT`: port used by `python main.py`

Targeted config overrides use the `AUDIO_ANALYZER__...` prefix.

Examples:

```bash
AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS=custom.local.yaml python main.py
```

```bash
AUDIO_ANALYZER__MODELS__ASR__DEVICE=GPU python main.py
```

## Key Sections

- `models.asr`: backend provider, model name, device, export precision, decoding settings
- `audio_preprocessing`: chunk size, silence detection, denoise settings, chunk directory
- `audio_util`: max file size, allowed extensions, upload read chunk size
- `pipeline.delete_chunks_after_use`: whether temporary chunks are removed after processing
- `sentiment`: enablement, provider, model, device, aggregation settings

## Common Values

- `models.asr.provider`: `openai` | `openvino` | `whispercpp`
- `models.asr.device`: typically `CPU`; `GPU` also works for supported OpenVINO paths
- `models.asr.weight_format`: optional OpenVINO export precision such as `int8`, `fp16`, or `null`
- `sentiment.enabled`: `true` or `false`
- `sentiment.provider`: `openvino` or `pytorch`
- `sentiment.weight_format`: optional OpenVINO export precision such as `int8`, `fp16`, or `null`

## Linux iGPU / OpenVINO GPU

If you want to use the Intel iGPU on Linux:

- on a new machine, first install the required Intel/OpenVINO host GPU runtime or oneAPI toolkit; `setvars.sh` is not present on a default Ubuntu install
- set `models.asr.device: GPU` for OpenVINO ASR
- set `sentiment.device: GPU` if you also want OpenVINO sentiment on GPU
- on systems that provide a oneAPI environment script, source the Intel environment before starting the service

Example:

```bash
source /opt/intel/oneapi/setvars.sh
python main.py
```

This GPU path was validated on the Linux host setup. The default Docker Compose setup does not automatically expose or configure iGPU access inside the container. The exact installation path can vary; `/opt/intel/oneapi/setvars.sh` is a common location, not a guaranteed one.
