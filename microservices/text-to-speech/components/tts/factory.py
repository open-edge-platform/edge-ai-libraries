from components.tts.base import TTSServiceConfig
from components.tts.openvino import IMPLEMENTATIONS as OPENVINO_IMPLEMENTATIONS
from components.tts.pytorch import IMPLEMENTATIONS as PYTORCH_IMPLEMENTATIONS


def _normalize_runtime(runtime_name: str | None) -> str:
    return (runtime_name or "pytorch").strip().lower()


_RUNTIME_IMPLEMENTATIONS = {
    "openvino": OPENVINO_IMPLEMENTATIONS,
    "pytorch": PYTORCH_IMPLEMENTATIONS,
}


def create_tts_service(**kwargs):
    config = TTSServiceConfig(
        session_id=kwargs["session_id"],
        model_name=kwargs["model_name"],
        runtime=_normalize_runtime(kwargs.get("runtime")),
        device=kwargs["device"],
        dtype=kwargs["dtype"],
        model_variant=kwargs["model_variant"],
        default_speaker=kwargs["default_speaker"],
        default_language=kwargs["default_language"],
    )

    implementations = _RUNTIME_IMPLEMENTATIONS.get(config.runtime)
    if implementations is None:
        raise ValueError(f"Unsupported TTS runtime: {config.runtime}")

    for implementation in implementations:
        if implementation.matches_model_name(config.model_name):
            return implementation.create_service(config)

    supported = ", ".join(implementation.IMPLEMENTATION_NAME for implementation in implementations)
    raise ValueError(
        f"No TTS implementation matched model '{config.model_name}' for runtime '{config.runtime}'. "
        f"Configured implementations: {supported}."
    )