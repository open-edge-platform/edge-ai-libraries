from components.tts.base import TTSServiceConfig, model_name_matches, normalize_model_name, raise_not_implemented


IMPLEMENTATION_NAME = "speecht5"


def matches_model_name(model_name: str) -> bool:
    normalized = normalize_model_name(model_name)
    return model_name_matches(normalized, "speecht5", "speech-t5") or normalized == "speech"


def create_service(config: TTSServiceConfig):
    raise_not_implemented("pytorch", IMPLEMENTATION_NAME, "components/tts/pytorch/speecht5.py")