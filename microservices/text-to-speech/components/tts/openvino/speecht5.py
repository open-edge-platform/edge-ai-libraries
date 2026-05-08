import threading

import numpy as np

from components.tts.base import BaseTTSService, TTSServiceConfig, model_name_matches, normalize_model_name
from components.tts.openvino import normalize_device
from utils.ensure_model import ensure_model, resolve_tts_model_source


IMPLEMENTATION_NAME = "speecht5"


def matches_model_name(model_name: str) -> bool:
    normalized = normalize_model_name(model_name)
    return model_name_matches(normalized, "speecht5", "speech-t5") or normalized == "speech"


def _speech_tensor_to_numpy(speech_tensor) -> np.ndarray:
    try:
        return np.asarray(speech_tensor.data, dtype=np.float32).reshape(-1)
    except RuntimeError as exc:
        if "Not Implemented" not in str(exc):
            raise

        import openvino as ov

        host_tensor = ov.Tensor(speech_tensor.get_element_type(), speech_tensor.get_shape())
        speech_tensor.copy_to(host_tensor)
        return np.asarray(host_tensor.data, dtype=np.float32).reshape(-1)


class OpenVinoSpeechT5Service(BaseTTSService):
    _models = {}
    _lock = threading.Lock()
    _default_sample_rate = 16000

    def __init__(self, config: TTSServiceConfig):
        super().__init__(config)
        model_key = self._get_model_key(IMPLEMENTATION_NAME)
        with OpenVinoSpeechT5Service._lock:
            if model_key not in OpenVinoSpeechT5Service._models:
                try:
                    import openvino_genai as ov_genai
                except ImportError as exc:
                    raise RuntimeError(
                        "OpenVINO GenAI runtime dependencies are not available. Install requirements.txt before starting the service."
                    ) from exc

                ensure_model()
                model_source = resolve_tts_model_source()
                OpenVinoSpeechT5Service._models[model_key] = ov_genai.Text2SpeechPipeline(
                    model_source,
                    normalize_device(config.device),
                )

        self.model = OpenVinoSpeechT5Service._models[model_key]
        self._inference_lock = self._get_inference_lock(IMPLEMENTATION_NAME)
        self.sample_rate = int(getattr(self.model, "sampling_rate", self._default_sample_rate))

    def synthesize(
        self,
        text: str,
        language: str | None = None,
        speaker: str | None = None,
        instructions: str | None = None,
    ) -> dict:
        normalized_text = self._validate_text(text)
        chosen_language, chosen_speaker = self._resolve_voice_request(language, speaker)

        if chosen_language and chosen_language.lower() != self.config.default_language.lower():
            raise ValueError(
                f"SpeechT5 currently supports only the configured language '{self.config.default_language}'."
            )
        if instructions:
            raise ValueError("SpeechT5 does not support free-form voice instructions.")

        with self._inference_lock:
            result = self.model.generate(normalized_text)
        audio = _speech_tensor_to_numpy(result.speeches[0])
        return self._build_result(audio, self.sample_rate, chosen_speaker, chosen_language, instructions)

    def get_model_info(self) -> dict:
        info = self._build_model_info(IMPLEMENTATION_NAME, self.model)
        info["supported_languages"] = [self.config.default_language]
        info["supported_speakers"] = [self.config.default_speaker]
        return info


def create_service(config: TTSServiceConfig):
    return OpenVinoSpeechT5Service(config)