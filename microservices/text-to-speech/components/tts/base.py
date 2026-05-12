from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
import threading

import numpy as np

from components.base_component import PipelineComponent
from utils.ensure_model import get_tts_model_path, resolve_tts_model_source


@dataclass(frozen=True)
class TTSServiceConfig:
    session_id: str
    model_name: str
    runtime: str
    device: str
    dtype: str
    model_variant: str
    default_speaker: str
    default_language: str


def normalize_model_name(model_name: str) -> str:
    return model_name.strip().lower()


def model_name_matches(model_name: str, *patterns: str) -> bool:
    normalized = normalize_model_name(model_name)
    return any(pattern in normalized for pattern in patterns)


_RUNTIME_LABELS = {"openvino": "OpenVINO", "pytorch": "PyTorch"}
_IMPL_LABELS = {"parler_tts": "Parler", "speecht5": "SpeechT5", "qwen_tts": "Qwen TTS"}


def raise_not_implemented(runtime: str, implementation: str, module_path: str) -> None:
    runtime_label = _RUNTIME_LABELS.get(runtime.lower(), runtime.capitalize())
    impl_label = _IMPL_LABELS.get(implementation, implementation.replace("_", " ").title())
    raise RuntimeError(
        f"TTS implementation '{implementation}' is not implemented for runtime '{runtime}'. "
        f"Add the {runtime_label} {impl_label} loader and synthesis adapter in {module_path}."
    )


class BaseTTSService(PipelineComponent, ABC):
    _inference_locks: dict[tuple[str, str, str, str, str], threading.Lock] = {}
    _inference_locks_guard = threading.Lock()

    def __init__(self, config: TTSServiceConfig):
        self.config = config

    @abstractmethod
    def synthesize(
        self,
        text: str,
        language: str | None = None,
        speaker: str | None = None,
        instructions: str | None = None,
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_model_info(self) -> dict:
        raise NotImplementedError

    def _build_result(
        self,
        audio: np.ndarray,
        sample_rate: int,
        speaker: str | None,
        language: str | None,
        instructions: str | None,
    ) -> dict:
        return {
            "audio": np.asarray(audio, dtype=np.float32),
            "sampling_rate": int(sample_rate),
            "duration": round(float(len(audio) / max(sample_rate, 1)), 3),
            "model": self.config.model_name,
            "variant": self.config.model_variant,
            "speaker": speaker,
            "language": language,
            "instructions": instructions,
        }

    def _validate_text(self, text: str) -> str:
        text = text.strip() if text else ""
        if not text:
            raise ValueError("Input text is required")
        return text

    def _resolve_voice_request(
        self,
        language: str | None,
        speaker: str | None,
    ) -> tuple[str, str]:
        return language or self.config.default_language, speaker or self.config.default_speaker

    def _get_model_key(self, implementation_name: str) -> tuple[str, str, str, str, str]:
        return (
            implementation_name,
            self.config.model_name,
            self.config.device,
            self.config.dtype,
            self.config.model_variant,
        )

    def _get_inference_lock(self, implementation_name: str) -> threading.Lock:
        model_key = self._get_model_key(implementation_name)
        with BaseTTSService._inference_locks_guard:
            if model_key not in BaseTTSService._inference_locks:
                BaseTTSService._inference_locks[model_key] = threading.Lock()
            return BaseTTSService._inference_locks[model_key]

    def _build_model_info(self, implementation: str, model) -> dict:
        def _get(attr):
            fn = getattr(model, attr, None)
            return list(fn()) if callable(fn) else []

        cache_dir = get_tts_model_path()
        return {
            "implementation": implementation,
            "model": self.config.model_name,
            "runtime": self.config.runtime,
            "variant": self.config.model_variant,
            "device": self.config.device,
            "dtype": self.config.dtype,
            "default_speaker": self.config.default_speaker,
            "default_language": self.config.default_language,
            "supported_speakers": _get("get_supported_speakers"),
            "supported_languages": _get("get_supported_languages"),
            "model_source": resolve_tts_model_source(),
            "local_checkpoint": cache_dir if os.path.isdir(cache_dir) and any(os.scandir(cache_dir)) else None,
        }