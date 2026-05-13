# Configuration

## Load Order

The service loads configuration in this order:

1. `config.yaml`
2. Files listed in `TEXT_TO_SPEECH_CONFIG_OVERRIDE_PATHS`
3. Environment variables with the `TEXT_TO_SPEECH__...` prefix

This applies to both Docker and standalone runs.

## Config Files

- `config.yaml`: base defaults for local or general use
- `config.container.yaml`: preferred container deployment config

For container deployments, edit `config.container.yaml` directly. For direct local runs, start from `config.yaml` and override only what you need.

## Environment Variables

- `TEXT_TO_SPEECH_CONFIG_PATH`: alternate base config file
- `TEXT_TO_SPEECH_CONFIG_OVERRIDE_PATHS`: comma-separated YAML override files
- `TEXT_TO_SPEECH_SERVER_HOST`: host used by `python main.py`
- `TEXT_TO_SPEECH_SERVER_PORT`: port used by `python main.py`

Targeted config overrides use the `TEXT_TO_SPEECH__...` prefix.

Examples:

```bash
TEXT_TO_SPEECH_CONFIG_OVERRIDE_PATHS=custom.local.yaml python main.py
```

```bash
TEXT_TO_SPEECH__MODELS__TTS__DEVICE=GPU python main.py
```

## Key Sections

- `models.tts`: model name, runtime, device, dtype, variant, speaker, language, cache settings
- `audio`: output format and sample width
- `pipeline.persist_outputs`: whether synthesized audio and metadata are written to storage

## Common Values

- `models.tts.runtime`: `openvino` or `pytorch`
- `models.tts.device`: `CPU`, `GPU`, or `NPU` depending on model/runtime support
- `models.tts.dtype`: `int8`, `int4`, `fp16`, `fp32`
- `models.tts.model_variant`: `custom_voice` or `voice_design` for Qwen variants
- `audio.output_format`: typically `wav`

## Linux iGPU / OpenVINO GPU

If you want to use the Intel iGPU on Linux:

- on a new machine, first install the required Intel/OpenVINO host GPU runtime or oneAPI toolkit; `setvars.sh` is not present on a default Ubuntu install
- set `models.tts.device: GPU` for OpenVINO TTS
- on systems that provide a oneAPI environment script, source the Intel environment before starting the service

Example:

```bash
source /opt/intel/oneapi/setvars.sh
python main.py
```

This GPU path was validated on the Linux host setup. The container path uses an Intel OpenVINO runtime base image plus `/dev/dri` passthrough, but it still depends on the host having working Intel GPU support. The exact installation path can vary; `/opt/intel/oneapi/setvars.sh` is a common location, not a guaranteed one.