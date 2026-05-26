import logging, os
from typing import Tuple
from utils.config_loader import config
from utils.cli_utils import run_cli
logger = logging.getLogger(__name__)

_WHISPER_CPP_MODEL_MAP = {
    "whisper-tiny":   "ggml-tiny.bin",
    "whisper-base":   "ggml-base.bin",
    "whisper-small":  "ggml-small.bin",
    "whisper-medium": "ggml-medium.bin",
    "whisper-large":  "ggml-large-v3.bin",
}


def _model_dir_name(model_name: str, weight_format: str | None = None) -> str:
    slug = model_name.replace('/', '_')
    if weight_format:
        return f"{slug}-{weight_format}"
    return slug

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

def _download_whispercpp_model(model_name: str, output_dir: str) -> bool:
    """Download a whisper.cpp GGUF model from HuggingFace."""
    filename = _WHISPER_CPP_MODEL_MAP.get(model_name)
    if not filename:
        raise ValueError(
            f"Unknown whisper.cpp model name: '{model_name}'. "
            f"Valid names: {list(_WHISPER_CPP_MODEL_MAP)}"
        )
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

    run_device = "cuda" if str(device).upper() == "GPU" else "cpu"
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
        output_dir = get_asr_model_path()
        _download_whispercpp_model(config.models.asr.name, output_dir)

    # Sentiment model download (if enabled)
    sent_cfg = getattr(config, "sentiment", None)
    if sent_cfg and getattr(sent_cfg, "enabled", False):
        ensure_sentiment_model()


def ensure_sentiment_model():
    """Download / export the sentiment model based on config.sentiment."""
    sent_cfg = config.sentiment
    model_name = sent_cfg.model                      # e.g. speechbrain/emotion-recognition-wav2vec2-IEMOCAP
    provider = getattr(sent_cfg, "provider", "openvino")
    models_base = getattr(sent_cfg, "models_base_path", "models")
    weight_format = getattr(sent_cfg, "weight_format", None)
    slug = _model_dir_name(model_name, weight_format if provider == "openvino" else None)
    output_dir = os.path.join(models_base, "sentiment", slug)

    if provider == "openvino":
        logger.info(f"Ensuring sentiment model (openvino): {model_name} → {output_dir}")
        if model_name.startswith("speechbrain/"):
            if weight_format:
                logger.warning("Ignoring sentiment.weight_format for SpeechBrain OpenVINO export; custom export path does not support it.")
            _export_speechbrain_sentiment_openvino(model_name, output_dir, getattr(sent_cfg, "device", "CPU"))
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
    weight_format = getattr(config.models.asr, "weight_format", None) if provider == "openvino" else None
    return os.path.join(
        config.models.asr.models_base_path,
        provider,
        _model_dir_name(config.models.asr.name, weight_format),
    )
