# System Requirements

## Hardware

- **CPU**: x86_64. Intel Core Ultra (Meteor Lake) or newer is recommended.
  Older Intel Core / Xeon processors will run the service but may be slower
  on OpenVINO inference paths.
- **Memory**: 16 GB RAM minimum. 32 GB recommended when using larger TTS
  models (for example Qwen variants) or when keeping multiple sessions
  warm.
- **Disk**: 20 GB free SSD space recommended for model assets, the Hugging
  Face cache, and per-session storage. NVMe is preferred for faster
  first-run model download and conversion.
- **GPU (optional)**: Intel integrated GPU (Meteor Lake or newer iGPU) or
  a supported discrete GPU exposed via `/dev/dri` for the OpenVINO `GPU`
  device path.
- **NPU (optional)**: Intel Core Ultra NPU is supported by OpenVINO for
  compatible models; set `models.tts.device` to `NPU` in config when
  available.

## Operating System

- Ubuntu 22.04 LTS (validated) or a compatible Linux distribution with a
  recent kernel.
- For container deployment: Docker Engine and Docker Compose v2.
- For GPU acceleration on Linux: Intel/OpenVINO host GPU runtime
  (e.g. `intel-opencl-icd`, `level-zero`) installed on the host. This is a
  separate prerequisite from the Python dependencies.

## Host Packages (Standalone Run)

The standalone path additionally requires:

```bash
sudo apt-get update
sudo apt-get install -y libsndfile1
```

## Python

- Python 3.10 or newer.
- Dependencies installed from `requirements.txt`.

## Network

- Outbound internet access on first run to download model assets from
  Hugging Face, unless models are pre-staged under `models/` and the cache.
- Inbound access to TCP port `8011` (default) for API clients.
