import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_EXPORT_REVISION = "2"

_REQUIRED_FILES = [
    "config.json",
    "checkpoint_path.txt",
    "openvino_export_revision.txt",
    "openvino_talker_language_model.xml",
    "openvino_talker_language_model.bin",
    "openvino_talker_embedding_model.xml",
    "openvino_talker_embedding_model.bin",
    "openvino_talker_text_embedding_model.xml",
    "openvino_talker_text_embedding_model.bin",
    "openvino_talker_text_projection_model.xml",
    "openvino_talker_text_projection_model.bin",
    "openvino_talker_code_predictor_embedding_model.xml",
    "openvino_talker_code_predictor_embedding_model.bin",
    "openvino_talker_code_predictor_model.xml",
    "openvino_talker_code_predictor_model.bin",
    os.path.join("speech_tokenizer", "config.json"),
    os.path.join("speech_tokenizer", "openvino_speech_tokenizer_encoder_model.xml"),
    os.path.join("speech_tokenizer", "openvino_speech_tokenizer_encoder_model.bin"),
    os.path.join("speech_tokenizer", "openvino_speech_tokenizer_decoder_model.xml"),
    os.path.join("speech_tokenizer", "openvino_speech_tokenizer_decoder_model.bin"),
]


def model_exists(output_dir: str) -> bool:
    if not all(os.path.exists(os.path.join(output_dir, f)) for f in _REQUIRED_FILES):
        return False
    revision_path = Path(output_dir) / "openvino_export_revision.txt"
    return revision_path.read_text(encoding="utf-8").strip() == _EXPORT_REVISION


def convert(model_name: str, output_dir: str, quantization_config: dict | None) -> None:
    if model_exists(output_dir):
        logger.info("Using cached OpenVINO TTS model at %s", output_dir)
        return

    if os.path.isdir(output_dir):
        logger.info("Removing stale Qwen OpenVINO export at %s", output_dir)
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    try:
        from utils.openvino_qwen3_tts_helper import convert_qwen3_tts_model
    except ImportError as exc:
        raise RuntimeError("Qwen OpenVINO helper not importable. Install requirements first.") from exc

    logger.info("Converting Qwen TTS model %s to OpenVINO IR at %s", model_name, output_dir)
    convert_qwen3_tts_model(model_name, output_dir, quantization_config=quantization_config, use_local_dir=False)

    Path(output_dir, "checkpoint_path.txt").write_text(f"{model_name}\n", encoding="utf-8")
    Path(output_dir, "openvino_export_revision.txt").write_text(f"{_EXPORT_REVISION}\n", encoding="utf-8")
