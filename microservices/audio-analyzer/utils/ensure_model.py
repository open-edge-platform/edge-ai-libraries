import logging, os
import yaml
from typing import Tuple
from utils.config_loader import config
from utils.cli_utils import run_cli
logger = logging.getLogger(__name__)

HF_PYTORCH_WEIGHTS_NAME = "pytorch_model.bin"

# openai-whisper stores model files as "<id>.pt" in the download_root directory.
_OPENAI_WHISPER_ID_MAP = {
    "whisper-tiny": "tiny",
    "whisper-base": "base",
    "whisper-small": "small",
    "whisper-medium": "medium",
    "whisper-large": "large-v3",
}


def _resolve_hf_token() -> str | None:
    """Return a valid HF token from config or the HF_TOKEN environment variable.

    Priority: ``models.asr.hf_token`` in config → ``HF_TOKEN`` env var.
    Returns ``None`` when no token is configured (public models only).
    """
    raw = getattr(config.models.asr, "hf_token", None)
    if isinstance(raw, str) and raw.lower() not in ("none", "null", ""):
        return raw
    env_token = os.environ.get("HF_TOKEN", "").strip()
    return env_token if env_token else None


def _download_hf_model(
    model_name: str,
    output_dir: str,
    hf_token: str = None,
    force: bool = False,
    required_files: list[str] | None = None,
) -> Tuple[bool, str]:
    """Download a HuggingFace model snapshot locally (offline-capable after first download)."""
    os.makedirs(output_dir, exist_ok=True)

    required_files = required_files or []
    has_required_files = all(
        os.path.exists(os.path.join(output_dir, f)) for f in required_files
    )

    if not force and os.listdir(output_dir) and has_required_files:
        logger.info("⚡ Using cached HF model at %s", output_dir)
        return True, output_dir

    if os.listdir(output_dir) and not has_required_files:
        logger.warning("Incomplete HF model cache detected at %s. Re-downloading.", output_dir)

    logger.info(
        "🚀 Downloading HF model %s → %s\n"
        "⏳ This may take time depending on model size…\n"
        "⚠️  Please do not terminate.",
        model_name, output_dir,
    )

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required. Run: pip install huggingface_hub") from exc

    try:
        snapshot_download(
            repo_id=model_name,
            local_dir=output_dir,
            local_dir_use_symlinks=False,
            token=hf_token,
        )
    except Exception as exc:
        logger.error("❌ HF download failed: %s", exc)
        return False, output_dir

    success = len(os.listdir(output_dir)) > 0
    logger.info("✅ Download successful" if success else "❌ Download incomplete")
    return success, output_dir


def _cache_diarization_dependencies_locally(pipeline_dir: str, hf_token: str = None) -> None:
    """Rewrite pyannote pipeline config.yaml so all sub-model refs point to local paths."""
    config_path = os.path.join(pipeline_dir, "config.yaml")
    if not os.path.exists(config_path):
        return

    with open(config_path, "r", encoding="utf-8") as fh:
        pipeline_cfg = yaml.safe_load(fh) or {}

    pipeline_params = pipeline_cfg.get("pipeline", {}).get("params", {})
    changed = False

    for key in ("segmentation", "embedding", "plda"):
        model_ref = pipeline_params.get(key)
        if not isinstance(model_ref, str):
            continue
        if os.path.isfile(model_ref) or os.path.isdir(model_ref):
            continue
        if "/" not in model_ref:
            continue

        # pyannote 4.x bundles sub-models inside the snapshot as "$model/<name>"
        if model_ref.startswith("$model/"):
            sub_name = model_ref[len("$model/"):]
            sub_dir = os.path.join(pipeline_dir, sub_name)
            local_checkpoint = os.path.join(sub_dir, HF_PYTORCH_WEIGHTS_NAME)
            if os.path.exists(local_checkpoint):
                pipeline_params[key] = local_checkpoint
                changed = True
            elif os.path.isdir(sub_dir):
                pipeline_params[key] = sub_dir
                changed = True
            continue

        # Standalone HF sub-model (pyannote 3.x style)
        dep_dir = os.path.join(pipeline_dir, "dependencies", model_ref.replace("/", "_"))
        success, _ = _download_hf_model(
            model_ref, dep_dir, hf_token=hf_token,
            required_files=[HF_PYTORCH_WEIGHTS_NAME, "config.yaml"],
        )
        if not success:
            continue
        checkpoint = os.path.join(dep_dir, HF_PYTORCH_WEIGHTS_NAME)
        if os.path.exists(checkpoint):
            pipeline_params[key] = checkpoint
            changed = True

    if changed:
        with open(config_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(pipeline_cfg, fh, sort_keys=False)


def get_diarization_model_path() -> str:
    diar_cfg = config.models.diarization
    return os.path.join(
        diar_cfg.models_base_path,
        diar_cfg.provider,
        diar_cfg.name.replace("/", "_"),
    )

_WHISPER_CPP_MODEL_MAP = {
    "whisper-tiny":   "ggml-tiny.bin",
    "whisper-base":   "ggml-base.bin",
    "whisper-small":  "ggml-small.bin",
    "whisper-medium": "ggml-medium.bin",
    "whisper-large":  "ggml-large-v3.bin",
    "whisper-turbo":  "ggml-large-v3-turbo.bin",
}

_WHISPER_CPP_DEFAULT_QUANTIZATION = {
    "whisper-tiny": "q5_1",
    "whisper-base": "q5_1",
    "whisper-small": "q5_1",
    "whisper-medium": "q5_0",
    "whisper-large": "q5_0",
    "whisper-turbo": "q5_0",
}

_WHISPER_CPP_SUPPORTED_QUANTIZATION = {
    "whisper-tiny": {"q5_1", "q8_0"},
    "whisper-base": {"q5_1", "q8_0"},
    "whisper-small": {"q5_1", "q8_0"},
    "whisper-medium": {"q5_0", "q8_0"},
    "whisper-large": {"q5_0"},
    "whisper-turbo": {"q5_0", "q8_0"},
}


def _normalize_whispercpp_weight_format(model_name: str, weight_format: str | None) -> str | None:
    if weight_format is None:
        return None

    normalized = str(weight_format).strip().lower()
    if normalized in {"", "none", "null", "default", "full", "fp16", "fp32"}:
        return None
    if normalized in {"int5", "q5"}:
        normalized = _WHISPER_CPP_DEFAULT_QUANTIZATION[model_name]
    elif normalized in {"int8", "q8"}:
        normalized = "q8_0"

    supported = _WHISPER_CPP_SUPPORTED_QUANTIZATION.get(model_name)
    if supported is None:
        raise ValueError(
            f"Unknown whisper.cpp model name: '{model_name}'. "
            f"Valid names: {list(_WHISPER_CPP_MODEL_MAP)}"
        )
    if normalized not in supported:
        raise ValueError(
            f"Unsupported whisper.cpp weight_format '{weight_format}' for {model_name}. "
            f"Supported values: null, q5/int5, q8/int8, and explicit {sorted(supported)}"
        )
    return normalized


def get_whispercpp_model_filename(model_name: str, weight_format: str | None = None) -> str:
    base_filename = _WHISPER_CPP_MODEL_MAP.get(model_name)
    if not base_filename:
        raise ValueError(
            f"Unknown whisper.cpp model name: '{model_name}'. "
            f"Valid names: {list(_WHISPER_CPP_MODEL_MAP)}"
        )

    quantized_suffix = _normalize_whispercpp_weight_format(model_name, weight_format)
    if not quantized_suffix:
        return base_filename

    stem, ext = os.path.splitext(base_filename)
    return f"{stem}-{quantized_suffix}{ext}"


def _model_dir_name(model_name: str, weight_format: str | None = None) -> str:
    slug = model_name.replace('/', '_')
    if weight_format:
        return f"{slug}-{weight_format}"
    return slug


def get_sentiment_model_path() -> str:
    sent_cfg = config.sentiment
    model_name = sent_cfg.model
    provider = getattr(sent_cfg, "provider", "openvino")
    models_base = getattr(sent_cfg, "models_base_path", "models")
    weight_format = getattr(sent_cfg, "weight_format", None)

    # SpeechBrain OpenVINO uses the custom export path below, which ignores
    # weight_format and expects the IR alongside the model snapshot files.
    include_weight_format = provider == "openvino" and not model_name.startswith("speechbrain/")
    slug = _model_dir_name(model_name, weight_format if include_weight_format else None)
    return os.path.join(models_base, "sentiment", slug)

def _ir_exists(output_dir: str) -> bool:
    """Check if exported OpenVINO IR files exist."""
    xml_file = os.path.join(output_dir, "openvino_model.xml")
    bin_file = os.path.join(output_dir, "openvino_model.bin")
    en_xml_file = os.path.join(output_dir, "openvino_encoder_model.xml")
    en_bin_file = os.path.join(output_dir, "openvino_encoder_model.bin")
    de_xml_file = os.path.join(output_dir, "openvino_decoder_model.xml")
    de_bin_file = os.path.join(output_dir, "openvino_decoder_model.bin")
    return (os.path.exists(xml_file) and os.path.exists(bin_file)) or (os.path.exists(en_xml_file) and os.path.exists(en_bin_file) and os.path.exists(de_xml_file) and os.path.exists(de_bin_file))

def _download_openvino_model(
    model_name: str,
    output_dir: str,
    weight_format: str,
    force: bool = False
) -> Tuple[bool, str]:
    """Export a HuggingFace model to OpenVINO IR using optimum-cli."""
    os.makedirs(output_dir, exist_ok=True)

    if not force and _ir_exists(output_dir):
        logger.info(f"⚡ Using cached export at {output_dir}")
        return True, output_dir

    cmd = [
        "optimum-cli", "export", "openvino",
        "--model", model_name,
        "--trust-remote-code",
        output_dir,
    ] + (["--weight-format", weight_format] if weight_format else [])

    logger.info(f"🚀  Exporting {model_name} → {output_dir} ({weight_format})\n"
                "⏳  Exporting model... This process may take some time depending on the model size. \n"
                "⚠️  Please do not terminate the process.")

    return_code = run_cli(cmd=cmd, log_fn=logger.info)
    if return_code != 0:
        logger.error(f"❌ Export failed: {return_code}")
        return False, output_dir

    success = _ir_exists(output_dir)
    logger.info("✅ Export successful" if success else "❌ Export incomplete")
    return success, output_dir

def _download_whispercpp_model(model_name: str, output_dir: str, weight_format: str | None = None) -> bool:
    """Download a whisper.cpp GGUF model from HuggingFace."""
    filename = get_whispercpp_model_filename(model_name, weight_format)
    dest = os.path.join(output_dir, filename)
    if os.path.isfile(dest):
        logger.info(f"⚡ Using cached whisper.cpp model at {dest}")
        return True

    os.makedirs(output_dir, exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required. Run: pip install huggingface_hub") from exc

    logger.info(f"⬇️  Downloading {filename} from ggerganov/whisper.cpp ...")
    hf_hub_download(repo_id="ggerganov/whisper.cpp", filename=filename, local_dir=output_dir)
    success = os.path.isfile(dest)
    logger.info("✅ Download complete" if success else "❌ Download incomplete")
    return success


def _download_speechbrain_model_snapshot(model_name: str, output_dir: str) -> None:
    marker = os.path.join(output_dir, "hyperparams.yaml")
    if os.path.isfile(marker):
        logger.info(f"⚡ SpeechBrain model already cached at {output_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required. Run: pip install huggingface_hub") from exc

    logger.info(f"⬇️  Downloading SpeechBrain model {model_name} ...")
    snapshot_download(repo_id=model_name, local_dir=output_dir)
    logger.info("✅ SpeechBrain model download complete")


def _export_speechbrain_sentiment_openvino(model_name: str, output_dir: str, device: str = "CPU") -> Tuple[bool, str]:
    _download_speechbrain_model_snapshot(model_name, output_dir)

    xml_path = os.path.join(output_dir, "openvino_model.xml")
    bin_path = os.path.join(output_dir, "openvino_model.bin")
    if os.path.isfile(xml_path) and os.path.isfile(bin_path):
        logger.info(f"⚡ Using cached SpeechBrain OpenVINO export at {output_dir}")
        return True, output_dir

    try:
        import openvino as ov
        import torch
        from speechbrain.inference.interfaces import foreign_class
    except ImportError as exc:
        raise RuntimeError(
            "openvino, torch, and speechbrain are required for SpeechBrain OpenVINO sentiment export."
        ) from exc

    logger.info(f"🚀  Converting SpeechBrain sentiment model to OpenVINO IR at {output_dir}")

    run_device = "cpu"
    classifier = foreign_class(
        source=output_dir,
        savedir=output_dir,
        pymodule_file="custom_interface.py",
        classname="CustomEncoderWav2vec2Classifier",
        run_opts={"device": run_device},
    )

    class WrappedEmotionModel(torch.nn.Module):
        def __init__(self, wrapped_classifier):
            super().__init__()
            self.classifier = wrapped_classifier

        def forward(self, wavs):
            out_prob, _, _, _ = self.classifier.classify_batch(wavs)
            return out_prob

    wrapped = WrappedEmotionModel(classifier)
    wrapped.eval()

    example = torch.zeros((1, 16000), dtype=torch.float32)
    ov_model = ov.convert_model(wrapped, example_input=example)
    ov.save_model(ov_model, xml_path)

    success = _ir_exists(output_dir)
    logger.info("✅ SpeechBrain OpenVINO export successful" if success else "❌ SpeechBrain OpenVINO export incomplete")
    return success, output_dir


def ensure_model():
    provider = config.models.asr.provider
    if provider == "openvino":
        output_dir = get_asr_model_path()
        weight_format = getattr(config.models.asr, "weight_format", None)
        _download_openvino_model(f"openai/{config.models.asr.name}", output_dir, weight_format)
    elif provider == "whispercpp":
        if str(getattr(config.models.asr, "device", "CPU")).upper() != "CPU":
            logger.warning("whispercpp backend is CPU-only; ignoring configured device %s", config.models.asr.device)
        output_dir = get_asr_model_path()
        weight_format = getattr(config.models.asr, "weight_format", None)
        _download_whispercpp_model(config.models.asr.name, output_dir, weight_format)
    elif provider == "openai":
        output_dir = get_asr_model_path()
        os.makedirs(output_dir, exist_ok=True)
        model_id = _OPENAI_WHISPER_ID_MAP.get(
            config.models.asr.name,
            config.models.asr.name.replace("whisper-", ""),
        )
        model_file = os.path.join(output_dir, f"{model_id}.pt")
        if os.path.isfile(model_file):
            logger.info("⚡ Using cached openai-whisper model at %s", model_file)
        else:
            logger.info(
                "🚀 Downloading openai-whisper model '%s' → %s\n"
                "⏳ This may take time depending on model size…\n"
                "⚠️  Please do not terminate.",
                model_id, output_dir,
            )
            try:
                import whisper as _whisper
                _whisper.load_model(model_id, device="cpu", download_root=output_dir)
                logger.info("✅ openai-whisper model download complete")
            except Exception as exc:
                logger.error("❌ openai-whisper model download failed: %s", exc)
                raise

    # Download diarization model when diarization is enabled
    if getattr(config.models.asr, "diarization", False):
        diar_cfg = getattr(config.models, "diarization", None)
        if diar_cfg and getattr(diar_cfg, "provider", None) == "huggingface":
            hf_token = _resolve_hf_token()
            output_dir = get_diarization_model_path()
            success, _ = _download_hf_model(
                diar_cfg.name,
                output_dir,
                hf_token=hf_token,
                required_files=["config.yaml"],
            )
            if success:
                _cache_diarization_dependencies_locally(output_dir, hf_token=hf_token)

    # Sentiment model download (if enabled)
    sent_cfg = getattr(config, "sentiment", None)
    if sent_cfg and getattr(sent_cfg, "enabled", False):
        ensure_sentiment_model()


def ensure_sentiment_model():
    """Download / export the sentiment model based on config.sentiment."""
    sent_cfg = config.sentiment
    model_name = sent_cfg.model                      # e.g. speechbrain/emotion-recognition-wav2vec2-IEMOCAP
    provider = getattr(sent_cfg, "provider", "openvino")
    weight_format = getattr(sent_cfg, "weight_format", None)
    output_dir = get_sentiment_model_path()

    if provider == "openvino":
        logger.info(f"Ensuring sentiment model (openvino): {model_name} → {output_dir}")
        if model_name.startswith("speechbrain/"):
            if weight_format:
                logger.warning("Ignoring sentiment.weight_format for SpeechBrain OpenVINO export; custom export path does not support it.")
            _export_speechbrain_sentiment_openvino(model_name, output_dir, "CPU")
        else:
            _download_openvino_model(model_name, output_dir, weight_format)
    elif provider == "pytorch":
        # SpeechBrain downloads from HF Hub automatically into savedir on first use;
        # pre-cache by snapshotting the repo if not already present.
        _download_speechbrain_model_snapshot(model_name, output_dir)
    else:
        raise ValueError(f"Unknown sentiment provider: {provider!r}")


def get_asr_model_path() -> str:
    provider = config.models.asr.provider
    if provider == "openvino":
        weight_format = getattr(config.models.asr, "weight_format", None)
    elif provider == "whispercpp":
        weight_format = _normalize_whispercpp_weight_format(
            config.models.asr.name,
            getattr(config.models.asr, "weight_format", None),
        )
    else:
        weight_format = None
    return os.path.join(
        config.models.asr.models_base_path,
        provider,
        _model_dir_name(config.models.asr.name, weight_format),
    )
