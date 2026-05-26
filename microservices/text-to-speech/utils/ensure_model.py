import logging
import os

from huggingface_hub import snapshot_download

from utils.config_loader import config

logger = logging.getLogger(__name__)

_DTYPE_MAP = {
    "float32": "fp32", "fp32": "fp32",
    "float16": "fp16", "fp16": "fp16",
    "int8": "int8", "int8_asym": "int8", "int8_sym": "int8",
    "int4": "int4", "int4_asym": "int4", "int4_sym": "int4",
}

_QUANTIZED_DTYPES = {"int8", "int8_asym", "int8_sym", "int4", "int4_asym", "int4_sym"}

_INT4_DTYPES = {"int4", "int4_asym", "int4_sym"}


def _runtime() -> str:
    return getattr(config.models.tts, "runtime", "pytorch").strip().lower()


def _model_name() -> str:
    return config.models.tts.name


def _requested_dtype() -> str:
    return getattr(config.models.tts, "dtype", "float32").strip().lower()


def _ov_dtype() -> str:
    return _DTYPE_MAP.get(_requested_dtype(), "fp32")


def _quantization_config() -> dict | None:
    dtype = _requested_dtype()
    if dtype not in _QUANTIZED_DTYPES:
        return None

    try:
        import nncf
    except ImportError as exc:
        raise RuntimeError("Quantized OpenVINO export requires NNCF. Install requirements first.") from exc

    mode = {
        "int8": "INT8_ASYM", "int8_asym": "INT8_ASYM", "int8_sym": "INT8_SYM",
        "int4": "INT4_ASYM", "int4_asym": "INT4_ASYM", "int4_sym": "INT4_SYM",
    }[dtype]
    cfg = {"mode": getattr(nncf.CompressWeightsMode, mode)}
    if dtype in _INT4_DTYPES:
        cfg["advanced_parameters"] = nncf.AdvancedCompressionParameters(
            group_size_fallback_mode=nncf.GroupSizeFallbackMode.ADJUST,
        )
    return cfg


def _is_model(name: str, *patterns: str) -> bool:
    n = name.strip().lower()
    return any(p in n for p in patterns)


def _openvino_model_exists(output_dir: str) -> bool:
    name = _model_name()
    if _is_model(name, "qwen3-tts"):
        from utils.ensure_qwen import model_exists
        return model_exists(output_dir)
    if _is_model(name, "speecht5"):
        from utils.ensure_speecht5 import model_exists
        return model_exists(output_dir)
    if _is_model(name, "parler"):
        from utils.ensure_parler import model_exists
        return model_exists(output_dir)
    raise ValueError(f"Unsupported OpenVINO TTS model: {name}")


def _convert_openvino_model(output_dir: str) -> None:
    name = _model_name()
    if _is_model(name, "qwen3-tts"):
        from utils.ensure_qwen import convert
        convert(name, output_dir, _quantization_config())
    elif _is_model(name, "speecht5"):
        from utils.ensure_speecht5 import convert
        convert(name, output_dir, _ov_dtype(), _quantization_config())
    elif _is_model(name, "parler"):
        from utils.ensure_parler import convert
        convert(name, output_dir, _quantization_config())
    else:
        raise ValueError(f"Unsupported OpenVINO TTS model: {name}")


def ensure_model() -> None:
    runtime = _runtime()

    if runtime == "openvino":
        _convert_openvino_model(get_tts_model_path())
        return

    if runtime != "pytorch":
        raise ValueError(f"Unsupported TTS runtime: {runtime}")

    if not config.models.tts.use_local_cache:
        return

    output_dir = get_tts_model_path()
    if os.path.isdir(output_dir) and any(os.scandir(output_dir)):
        logger.info("Using cached TTS checkpoint at %s", output_dir)
        return

    os.makedirs(output_dir, exist_ok=True)
    try:
        logger.info("Downloading TTS model %s to %s", _model_name(), output_dir)
        snapshot_download(repo_id=_model_name(), local_dir=output_dir, local_dir_use_symlinks=False)
    except Exception as exc:
        logger.warning("Model prefetch skipped: %s", exc)


def get_tts_model_path() -> str:
    runtime = _runtime()
    safe_name = _model_name().replace("/", "_")
    if runtime == "openvino":
        safe_name = f"{safe_name}__{_ov_dtype()}"
    return os.path.join(config.models.tts.models_base_path, runtime, safe_name)


def resolve_tts_model_source() -> str:
    output_dir = get_tts_model_path()
    runtime = _runtime()
    if runtime == "openvino" and _openvino_model_exists(output_dir):
        return output_dir
    if runtime == "pytorch" and os.path.isdir(output_dir) and any(os.scandir(output_dir)):
        return output_dir
    return _model_name()
