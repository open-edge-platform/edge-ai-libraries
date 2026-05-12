import threading

from components.tts.base import BaseTTSService, TTSServiceConfig, model_name_matches, normalize_model_name
from components.tts.openvino import normalize_device
from utils.ensure_model import ensure_model, resolve_tts_model_source


IMPLEMENTATION_NAME = "qwen_tts"


def matches_model_name(model_name: str) -> bool:
    normalized = normalize_model_name(model_name)
    return normalized.startswith("qwen/") or model_name_matches(normalized, "qwen3-tts")


class OpenVinoQwenTTSService(BaseTTSService):
    _models = {}
    _lock = threading.Lock()

    def __init__(self, config: TTSServiceConfig):
        super().__init__(config)
        model_key = self._get_model_key(IMPLEMENTATION_NAME)
        with OpenVinoQwenTTSService._lock:
            if model_key not in OpenVinoQwenTTSService._models:
                try:
                    from utils.openvino_qwen3_tts_helper import OVQwen3TTSModel
                except ImportError as exc:
                    raise RuntimeError(
                        "OpenVINO runtime dependencies are not available. Install requirements.txt before starting the service."
                    ) from exc

                ensure_model()
                model_source = resolve_tts_model_source()
                OpenVinoQwenTTSService._models[model_key] = OVQwen3TTSModel.from_pretrained(
                    model_dir=model_source,
                    device=normalize_device(config.device),
                )

        self.model = OpenVinoQwenTTSService._models[model_key]
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

        with self._inference_lock:
            if self.config.model_variant == "custom_voice":
                wavs, sample_rate = self.model.generate_custom_voice(
                    text=normalized_text,
                    language=chosen_language,
                    speaker=chosen_speaker,
                    instruct=instructions or "",
                )
            elif self.config.model_variant == "voice_design":
                wavs, sample_rate = self.model.generate_voice_design(
                    text=normalized_text,
                    language=chosen_language,
                    instruct=instructions or "",
                )
            else:
                raise ValueError(
                    f"Unsupported configured model_variant: {self.config.model_variant}. Use custom_voice or voice_design."
                )

        return self._build_result(wavs[0], sample_rate, chosen_speaker, chosen_language, instructions)

    def get_model_info(self) -> dict:
        return self._build_model_info(IMPLEMENTATION_NAME, self.model)


def create_service(config: TTSServiceConfig):
    return OpenVinoQwenTTSService(config)