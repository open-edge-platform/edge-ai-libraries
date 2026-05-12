import logging
import os

logger = logging.getLogger(__name__)


def model_exists(output_dir: str) -> bool:
    try:
        from utils.openvino_parler_tts_helper import parler_openvino_model_exists
    except ImportError as exc:
        raise RuntimeError("Parler OpenVINO helper not available. Install requirements first.") from exc
    return parler_openvino_model_exists(output_dir)


def convert(model_name: str, output_dir: str, quantization_config: dict | None) -> None:
    if model_exists(output_dir):
        logger.info("Using cached OpenVINO TTS model at %s", output_dir)
        return

    os.makedirs(output_dir, exist_ok=True)

    try:
        from utils.openvino_parler_tts_helper import convert_parler_tts_model
    except ImportError as exc:
        raise RuntimeError("Parler OpenVINO export dependencies not available. Install requirements first.") from exc

    logger.info("Exporting Parler model %s to OpenVINO IR at %s", model_name, output_dir)
    convert_parler_tts_model(model_name, output_dir, quantization_config=quantization_config)
