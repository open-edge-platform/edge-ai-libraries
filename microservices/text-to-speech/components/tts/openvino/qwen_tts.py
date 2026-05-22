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

    def _validate_custom_voice_request(self, speaker: str | None) -> None:
        if not speaker:
            raise ValueError("Qwen custom_voice requires a speaker name.")

        get_supported_speakers = getattr(self.model, "get_supported_speakers", None)
        if not callable(get_supported_speakers):
            return

        supported_speakers = [candidate.strip() for candidate in get_supported_speakers() if candidate and candidate.strip()]
        if supported_speakers and speaker.strip().lower() not in {candidate.lower() for candidate in supported_speakers}:
            raise ValueError(
                f"Unsupported voice '{speaker}'. Supported voices: {', '.join(supported_speakers)}."
            )

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
                self._validate_custom_voice_request(chosen_speaker)
                wavs, sample_rate = self.model.generate_custom_voice(
                    text=normalized_text,
                    language=chosen_language,
                    speaker=chosen_speaker,
                    instruct=instructions or "",
                )
            elif self.config.model_variant == "voice_design":
                if chosen_speaker and chosen_speaker.strip() and chosen_speaker != self.config.default_speaker:
                    raise ValueError(
                        "Qwen voice_design does not accept the voice field. Describe the desired voice in instructions instead."
                    )
                if not instructions:
                    raise ValueError("Qwen voice_design requires instructions describing the desired voice.")
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