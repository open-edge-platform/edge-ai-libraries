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

- `models.tts`: model name, runtime, device, dtype, variant, speaker, English language default, cache settings
- `audio`: output format and sample width
- `pipeline.persist_outputs`: whether synthesized audio and metadata are written to storage

## Common Values

- `models.tts.runtime`: `openvino` or `pytorch`
- `models.tts.device`: `CPU`, `GPU`, or `NPU` depending on model/runtime support
- `models.tts.dtype`: `int8`, `int4`, `fp16`, `fp32`
- `models.tts.model_variant`: `custom_voice` or `voice_design` for Qwen variants
- `models.tts.default_language`: keep this at `English`; other languages are not currently supported by the service API
- `audio.output_format`: typically `wav`

## Linux iGPU / OpenVINO GPU

To use the Intel iGPU on Linux:

- Install the required Intel/OpenVINO host GPU runtime
  (e.g. `intel-opencl-icd`, `level-zero`) on the host machine.
- Set `models.tts.device: GPU` for OpenVINO TTS.

This GPU path was validated on the Linux host setup. The container path
uses an Intel OpenVINO runtime base image plus `/dev/dri` passthrough, but
it still depends on the host having working Intel GPU support.