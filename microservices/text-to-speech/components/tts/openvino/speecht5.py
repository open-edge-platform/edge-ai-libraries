import logging
import threading

import numpy as np

from components.tts import speecht5_voices
from components.tts.base import BaseTTSService, TTSServiceConfig, model_name_matches, normalize_model_name
from components.tts.openvino import normalize_device
from components.tts.text_normalizer import normalize_for_speech
from utils.ensure_model import ensure_model, resolve_tts_model_source


logger = logging.getLogger(__name__)


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

    def _speaker_embedding_tensor(self, speaker: str):
        """Build the OpenVINO tensor carrying the requested voice's x-vector.

        Without this the pipeline silently falls back to CMU Arctic vector
        7306, which is the thin default the kiosk used to ship.
        """
        import openvino as ov

        embedding = speecht5_voices.load_embedding(speaker)
        # ov.Tensor does not copy, and the cached array is read-only, so hand
        # over a writable copy the runtime can own.
        return ov.Tensor(np.array(embedding, dtype=np.float32))

    def synthesize(
        self,
        text: str,
        language: str | None = None,
        speaker: str | None = None,
        instructions: str | None = None,
    ) -> dict:
        normalized_text = self._validate_text(text)
        # SpeechT5's character vocabulary has no digits or currency symbols, so
        # they are tokenised as <unk> and dropped from the audio entirely
        # ("open 8 AM to 11 PM" is spoken as "open AM to PM"). Expand them to
        # words before synthesis.
        spoken_text = normalize_for_speech(normalized_text)
        if not spoken_text:
            raise ValueError("Input text contains no pronounceable characters")
        if spoken_text != normalized_text:
            logger.debug(
                "[SPEECHT5] Normalised text for synthesis: %r -> %r",
                normalized_text, spoken_text,
            )
        chosen_language, chosen_speaker = self._resolve_voice_request(language, speaker)

        if chosen_language and chosen_language.lower() != self.config.default_language.lower():
            raise ValueError(
                f"Only {self.config.default_language} is currently supported for speech synthesis."
            )
        if instructions:
            raise ValueError("SpeechT5 does not support free-form voice instructions.")

        voice = speecht5_voices.resolve_voice(chosen_speaker)
        speaker_embedding = self._speaker_embedding_tensor(voice.name)

        with self._inference_lock:
            result = self.model.generate(spoken_text, speaker_embedding)
        audio = _speech_tensor_to_numpy(result.speeches[0])
        return self._build_result(audio, self.sample_rate, voice.name, chosen_language, instructions)

    def get_model_info(self) -> dict:
        info = self._build_model_info(IMPLEMENTATION_NAME, self.model)
        info["supported_languages"] = [self.config.default_language]
        info["supported_speakers"] = speecht5_voices.supported_speakers()
        info["voices"] = speecht5_voices.describe_speakers()
        return info


def create_service(config: TTSServiceConfig):
    return OpenVinoSpeechT5Service(config)