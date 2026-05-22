import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_VOCODER = "microsoft/speecht5_hifigan"

_REQUIRED_FILES = [
    "config.json",
    "generation_config.json",
    "openvino_encoder_model.xml",
    "openvino_encoder_model.bin",
    "openvino_decoder_model.xml",
    "openvino_decoder_model.bin",
    "openvino_postnet.xml",
    "openvino_postnet.bin",
    "openvino_vocoder.xml",
    "openvino_vocoder.bin",
    "openvino_tokenizer.xml",
    "openvino_tokenizer.bin",
]


def model_exists(output_dir: str) -> bool:
    return all(os.path.exists(os.path.join(output_dir, f)) for f in _REQUIRED_FILES)


def convert(model_name: str, output_dir: str, ov_dtype: str, quantization_config: dict | None) -> None:
    if model_exists(output_dir):
        logger.info("Using cached OpenVINO TTS model at %s", output_dir)
        return

    os.makedirs(output_dir, exist_ok=True)

    try:
        from openvino import Core, save_model
        from openvino_tokenizers import convert_tokenizer
        from optimum.exporters.openvino import main_export
        from optimum.intel.openvino import OVConfig
        from transformers import AutoTokenizer
        import nncf
    except ImportError as exc:
        raise RuntimeError("SpeechT5 OpenVINO export dependencies not available. Install requirements first.") from exc

    logger.info("Exporting SpeechT5 model %s to OpenVINO IR at %s", model_name, output_dir)
    main_export(
        model_name,
        output_dir,
        task="text-to-audio",
        model_kwargs={"vocoder": _VOCODER},
        trust_remote_code=False,
        convert_tokenizer=False,
        ov_config=OVConfig(dtype=ov_dtype),
    )

    if quantization_config is not None:
        ov_core = Core()
        for model_file in ("openvino_encoder_model.xml", "openvino_decoder_model.xml", "openvino_postnet.xml", "openvino_vocoder.xml"):
            model_path = Path(output_dir) / model_file
            quantized = nncf.compress_weights(ov_core.read_model(model_path), **quantization_config)
            tmp = model_path.with_name(f"{model_path.stem}__q.xml")
            save_model(quantized, tmp)
            tmp.replace(model_path)
            tmp.with_suffix(".bin").replace(model_path.with_suffix(".bin"))

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    ov_tok = convert_tokenizer(tokenizer)
    save_model(
        ov_tok[0] if isinstance(ov_tok, tuple) else ov_tok,
        Path(output_dir) / "openvino_tokenizer.xml",
        compress_to_fp16=(ov_dtype == "fp16"),
    )
