# System Requirements

## Hardware

- **CPU**: x86_64. Modern Intel Core or Xeon processor recommended.
- **Memory**: 8 GB RAM minimum; 16 GB recommended for larger ASR models or
  sentiment + ASR running together.
- **Disk**: At least 10 GB free for model assets, Hugging Face cache,
  temporary chunks, and session storage.
- **GPU (optional)**: Intel integrated GPU or discrete GPU exposed via
  `/dev/dri` for the OpenVINO `GPU` device path.
- **Microphone (optional)**: ALSA-compatible capture device if you intend to
  list devices via `GET /devices` or pass `/dev/snd` into the container.

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
sudo apt-get install -y ffmpeg alsa-utils libsndfile1
```

## Python

- Python 3.10 or newer.
- Dependencies installed from `requirements.txt`.

## Network

- Outbound internet access on first run to download model assets from
  Hugging Face, unless models are pre-staged under `models/` and the cache.
- Inbound access to TCP port `8010` (default) for API clients.

## Optional: Intel oneAPI

If your Linux iGPU setup provides an Intel oneAPI environment script, it must
be sourced before starting the service:

```bash
source /opt/intel/oneapi/setvars.sh
```

This script is not present on a default Ubuntu install; it appears only after
the relevant Intel host stack is installed.
