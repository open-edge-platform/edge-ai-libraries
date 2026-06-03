# Configuration

## Load Order

The service loads configuration in this order:

1. `config.yaml`
2. Environment variables with the `AUDIO_ANALYZER__...` prefix

The same `config.yaml` is used for both Docker and standalone runs. In Docker, `config.yaml` is bind-mounted into the container, so edits on the host take effect on `docker compose restart`.

## Config File

- `config.yaml`: single source of truth for both standalone and container runs.

## Environment Variables

- `AUDIO_ANALYZER_CONFIG_PATH`: alternate base config file (advanced)
- `AUDIO_ANALYZER_ENV_FILE`: optional `.env` file to preload before config parsing
- `AUDIO_ANALYZER_SERVER_HOST`: host used by `python main.py`
- `AUDIO_ANALYZER_SERVER_PORT`: port used by `python main.py`

Targeted config overrides use the `AUDIO_ANALYZER__...` prefix.

Example:

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
- `models.asr.device`: typically `CPU`; `GPU` works only for supported OpenVINO paths
- `models.asr.weight_format`: OpenVINO export precision such as `int8`, `fp16`, or `null`; for `whispercpp`, quantization such as `q5`, `q5_0`, `q5_1`, `q8`, `q8_0`, `int5`, `int8`, or `null`
- `sentiment.enabled`: `true` or `false`
- `sentiment.provider`: `openvino` or `pytorch`
- `sentiment.weight_format`: optional OpenVINO export precision such as `int8`, `fp16`, or `null`

## ASR Provider Notes

- `openai`: uses `openai-whisper` and downloads PyTorch Whisper weights on first use.
- `openvino`: exports the configured Whisper model to OpenVINO IR under `models/openvino/...` and can target `CPU` or `GPU`.
- `whispercpp`: downloads the matching whisper.cpp `ggml` model under `models/whispercpp/...` and runs on `CPU` only.

Provider-specific `models.asr` fields:

- `weight_format`: used by `openvino` for IR export precision and by `whispercpp` for model quantization.
- `beam_size`, `best_of`, `threads`, `word_timestamps`: used only by `whispercpp`.
