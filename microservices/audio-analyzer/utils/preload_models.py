import logging
import tempfile
import wave
from pathlib import Path

from components.asr_component import ASRComponent
from utils.config_loader import config

logger = logging.getLogger(__name__)


def _write_silent_wav(path: str, seconds: float = 1.0, sample_rate: int = 16000) -> None:
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * int(seconds * sample_rate))


def preload_models():
    # Load the default ASR model into memory.
    component = ASRComponent(session_id="startup", provider=config.models.asr.provider, model_name=config.models.asr.name, device=config.models.asr.device)
    # Warm it with one throwaway transcription so the first real request does not
    # pay the model's one-time compilation/JIT cost (otherwise ~10x slower).
    try:
        warmup_wav = Path(tempfile.gettempdir()) / "asr_warmup.wav"
        _write_silent_wav(str(warmup_wav))
        component.asr.transcribe(str(warmup_wav), temperature=0.0, language=None)
        warmup_wav.unlink(missing_ok=True)
        logger.info("ASR warmup transcription completed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ASR warmup failed (non-fatal): %s", exc)
