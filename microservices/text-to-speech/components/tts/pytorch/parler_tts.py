import logging
import threading
from contextlib import contextmanager

import torch

from components.tts.base import BaseTTSService, TTSServiceConfig, model_name_matches, normalize_model_name
from components.tts.pytorch import normalize_device, resolve_dtype
from utils.ensure_model import resolve_tts_model_source
from utils.parler_tts_compat import patch_parler_tts_compat


IMPLEMENTATION_NAME = "parler_tts"

SUPPORTED_SPEAKERS = [
    "Laura",
    "Gary",
    "Jon",
    "Lea",
    "Karen",
    "Rick",
    "Brenda",
    "David",
    "Eileen",
    "Jordan",
    "Mike",
    "Yann",
    "Joy",
    "James",
    "Eric",
    "Lauren",
    "Rose",
    "Will",
    "Jason",
    "Aaron",
    "Naomie",
    "Alisa",
    "Patrick",
    "Jerry",
    "Tina",
    "Jenna",
    "Bill",
    "Tom",
    "Carol",
    "Barbara",
    "Rebecca",
    "Anna",
    "Bruce",
    "Emily",
]

_PARLER_LOGGER_NAME = "parler_tts.modeling_parler_tts"
_PROMPT_MASK_WARNING = (
    "`prompt_attention_mask` is specified but `attention_mask` is not. "
    "A full `attention_mask` will be created. Make sure this is the intended behaviour."
)


def matches_model_name(model_name: str) -> bool:
    return model_name_matches(normalize_model_name(model_name), "parler")


def _build_voice_description(speaker: str, language: str, instructions: str | None) -> str:
    voice_name = speaker.strip() if speaker else "A speaker"
    if voice_name.lower() == "default":
        voice_name = "A speaker"

    description_parts = [
        f"{voice_name}'s voice is clear and natural in {language}.",
        "The recording is clean, close-mic, and free of background noise.",
    ]
    if instructions:
        description_parts.append(instructions.strip().rstrip("."))
    return " ".join(description_parts)


@contextmanager
def _suppress_prompt_attention_mask_warning():
    logger = logging.getLogger(_PARLER_LOGGER_NAME)

    class _PromptMaskFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return record.getMessage() != _PROMPT_MASK_WARNING

    log_filter = _PromptMaskFilter()
    logger.addFilter(log_filter)
    try:
        yield
    finally:
        logger.removeFilter(log_filter)


class PyTorchParlerTTSService(BaseTTSService):
    _models = {}
    _lock = threading.Lock()

    def __init__(self, config: TTSServiceConfig):
        super().__init__(config)
        model_key = self._get_model_key(IMPLEMENTATION_NAME)
        with PyTorchParlerTTSService._lock:
            if model_key not in PyTorchParlerTTSService._models:
                try:
                    patch_parler_tts_compat()
                    from parler_tts import ParlerTTSForConditionalGeneration
                    from transformers import AutoTokenizer
                except ImportError as exc:
                    raise RuntimeError(
                        "parler-tts is not installed. Install dependencies from requirements.txt before starting the service."
                    ) from exc

                device = normalize_device(config.device)
                dtype = resolve_dtype(config.dtype, cpu_fallback=(device == "cpu"))
                model_source = resolve_tts_model_source()
                model = ParlerTTSForConditionalGeneration.from_pretrained(
                    model_source,
                    torch_dtype=dtype,
                ).to(device)
                tokenizer = AutoTokenizer.from_pretrained(model_source)
                PyTorchParlerTTSService._models[model_key] = {
                    "model": model,
                    "tokenizer": tokenizer,
                    "device": device,
                }

        artifacts = PyTorchParlerTTSService._models[model_key]
        self.model = artifacts["model"]
        self.tokenizer = artifacts["tokenizer"]
        self.device = artifacts["device"]
        self.sample_rate = int(getattr(self.model.config, "sampling_rate", 44100))
        self._inference_lock = self._get_inference_lock(IMPLEMENTATION_NAME)

    def synthesize(
        self,
        text: str,
        language: str | None = None,
        speaker: str | None = None,
        instructions: str | None = None,
    ) -> dict:
        normalized_text = self._validate_text(text)
        chosen_language, chosen_speaker = self._resolve_voice_request(language, speaker)
        description = _build_voice_description(chosen_speaker, chosen_language, instructions)

        description_inputs = self.tokenizer(description, return_tensors="pt")
        prompt_inputs = self.tokenizer(normalized_text, return_tensors="pt")
        input_ids = description_inputs.input_ids.to(self.device)
        attention_mask = description_inputs.attention_mask.to(self.device)
        prompt_input_ids = prompt_inputs.input_ids.to(self.device)
        prompt_attention_mask = prompt_inputs.attention_mask.to(self.device)

        with self._inference_lock:
            with torch.inference_mode(), _suppress_prompt_attention_mask_warning():
                generation = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    prompt_input_ids=prompt_input_ids,
                    prompt_attention_mask=prompt_attention_mask,
                )

        audio = generation.detach().cpu().numpy().reshape(-1)
        return self._build_result(audio, self.sample_rate, chosen_speaker, chosen_language, instructions)

    def get_model_info(self) -> dict:
        info = self._build_model_info(IMPLEMENTATION_NAME, self.model)
        info["supported_speakers"] = SUPPORTED_SPEAKERS
        return info


def create_service(config: TTSServiceConfig):
    return PyTorchParlerTTSService(config)