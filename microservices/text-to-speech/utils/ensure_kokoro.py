"""Download and locate the Kokoro-82M ONNX model and combined voices file.

Kokoro runs through ``kokoro-onnx`` on onnxruntime (CPU), independent of the
OpenVINO/PyTorch runtimes used by the other TTS backends. The two asset files
are published on the kokoro-onnx GitHub release and are fetched once into the
shared models cache.
"""
import logging
import os

import requests

from utils.config_loader import config

logger = logging.getLogger(__name__)

MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"

_RELEASE_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_DOWNLOADS = {
    MODEL_FILE: f"{_RELEASE_BASE}/{MODEL_FILE}",
    VOICES_FILE: f"{_RELEASE_BASE}/{VOICES_FILE}",
}


def model_dir() -> str:
    """Directory that holds the Kokoro ONNX assets."""
    return os.path.join(config.models.tts.models_base_path, "kokoro")


def model_paths() -> tuple[str, str]:
    """Return ``(model_path, voices_path)`` for the Kokoro assets."""
    base = model_dir()
    return os.path.join(base, MODEL_FILE), os.path.join(base, VOICES_FILE)


def model_exists(output_dir: str | None = None) -> bool:
    base = output_dir or model_dir()
    return all(os.path.exists(os.path.join(base, name)) for name in (MODEL_FILE, VOICES_FILE))


def _download(url: str, destination: str) -> None:
    tmp = destination + ".part"
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with open(tmp, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                if chunk:
                    handle.write(chunk)
    os.replace(tmp, destination)


def ensure_kokoro() -> tuple[str, str]:
    """Download the Kokoro model and voices if absent; return their paths."""
    base = model_dir()
    os.makedirs(base, exist_ok=True)
    for filename, url in _DOWNLOADS.items():
        destination = os.path.join(base, filename)
        if os.path.exists(destination):
            continue
        logger.info("Downloading Kokoro asset %s from %s", filename, url)
        _download(url, destination)
    return model_paths()
