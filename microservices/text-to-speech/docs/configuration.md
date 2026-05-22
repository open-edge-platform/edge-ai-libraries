# Configuration

## Load Order

The service loads configuration in this order:

1. `config.yaml`
2. Environment variables with the `TEXT_TO_SPEECH__...` prefix

The same `config.yaml` is used for both Docker and standalone runs. In Docker, `config.yaml` is bind-mounted into the container, so edits on the host take effect on `docker compose restart`.

## Config File

- `config.yaml`: single source of truth for both standalone and container runs.

## Environment Variables

- `TEXT_TO_SPEECH_CONFIG_PATH`: alternate base config file (advanced)
- `TEXT_TO_SPEECH_SERVER_HOST`: host used by `python main.py`
- `TEXT_TO_SPEECH_SERVER_PORT`: port used by `python main.py`

Targeted config overrides use the `TEXT_TO_SPEECH__...` prefix.

Example:

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