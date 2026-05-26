import threading

from components.tts.base import BaseTTSService, TTSServiceConfig, model_name_matches, normalize_model_name
from components.tts.openvino import normalize_device
from utils.ensure_model import ensure_model, resolve_tts_model_source


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


class OpenVinoParlerTTSService(BaseTTSService):
    _models = {}
    _lock = threading.Lock()

    def __init__(self, config: TTSServiceConfig):
        super().__init__(config)
        model_key = self._get_model_key(IMPLEMENTATION_NAME)
        with OpenVinoParlerTTSService._lock:
            if model_key not in OpenVinoParlerTTSService._models:
                try:
                    from utils.openvino_parler_tts_helper import OVParlerTTSModel
                except ImportError as exc:
                    raise RuntimeError(
                        "OpenVINO Parler runtime dependencies are not available. Install requirements.txt before starting the service."
                    ) from exc

                ensure_model()
                model_source = resolve_tts_model_source()
                OpenVinoParlerTTSService._models[model_key] = OVParlerTTSModel.from_pretrained(
                    model_dir=model_source,
                    device=normalize_device(config.device),
                )

        self.model = OpenVinoParlerTTSService._models[model_key]
        self.sample_rate = int(self.model.sample_rate)
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
        with self._inference_lock:
            audio, sample_rate = self.model.generate(normalized_text, description)
        return self._build_result(audio, sample_rate, chosen_speaker, chosen_language, instructions)

    def get_model_info(self) -> dict:
        info = self._build_model_info(IMPLEMENTATION_NAME, self.model)
        info["supported_speakers"] = SUPPORTED_SPEAKERS
        return info


def create_service(config: TTSServiceConfig):
    return OpenVinoParlerTTSService(config)