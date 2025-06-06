from enum import Enum

class DeviceType(str, Enum):
    """Enum for the device types available for transcription"""
    CPU = "cpu"
    GPU = "gpu"   #TODO Enable GPU support
    AUTO = "auto"

class WhisperModel(str, Enum):
    """Enum for the available Whisper model variants"""
    TINY = "tiny"
    TINY_EN = "tiny.en"
    BASE = "base"
    BASE_EN = "base.en"
    SMALL = "small"
    SMALL_EN = "small.en"
    MEDIUM = "medium"
    MEDIUM_EN = "medium.en"
    LARGE_V1 = "large-v1"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"
    #TODO Add support for distill-whisper models
    
    @property
    def display_name(self) -> str:
        """Return a user-friendly display name for the model"""
        display_names = {
            "tiny": "Tiny (Multilingual)",
            "tiny.en": "Tiny (English)",
            "base": "Base (Multilingual)",
            "base.en": "Base (English)",
            "small": "Small (Multilingual)",
            "small.en": "Small (English)",
            "medium": "Medium (Multilingual)",
            "medium.en": "Medium (English)",
            "large-v1": "Large v1",
            "large-v2": "Large v2",
            "large-v3": "Large v3"
        }
        return display_names.get(self.value, self.value)
    
    @property
    def description(self) -> str:
        """Return a description of the model including size and language support"""
        descriptions = {
            "tiny": "Multilingual tiny sized whisper model. Significantly less accuracy, extremely fast inference.",
            "tiny.en": "English only version of tiny whisper model. Significantly less accuracy, extremely fast inference.",
            "base": "Multilingual base whisper model.",
            "base.en": "English only version of base whisper model.",
            "small": "Multilingual small sized whisper model. Good accuracy. Fast inference.",
            "small.en": "English only version of small whisper Model. Good accuracy. Fast inference.",
            "medium": "Multilingual medium sized whisper model. Very good accuracy. Longer inference time.",
            "medium.en": "English only version of Medium whisper Model. Very good accuracy. Longer inference time.",
            "large-v1": "Version 1 of large multilingual whisper model. Extremely high accuracy. Very slow inference time.",
            "large-v2": "Version 2 of large multilingual whisper model. Extremely high accuracy. Very slow inference time.",
            "large-v3": "Version 3 of large multilingual whisper model. Extremely high accuracy. Very slow inference time."
        }
        return descriptions.get(self.value, "No description available")
        
    def to_dict(self) -> dict:
        """Return all model information as a dictionary"""
        return {
            "model_id": self.value,
            "display_name": self.display_name,
            "description": self.description
        }

class TranscriptionStatus(str, Enum):
    """Enum for the status of a transcription job"""
    #TODO Use this type in asynchronous API design,if required. Currently, only COMPLETED status is used.
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptionBackend(str, Enum):
    """Available transcription backends"""
    WHISPER_CPP = "whisper_cpp"
    OPENVINO = "openvino"

class StorageBackend(str, Enum):
    """Available storage backends for handling files and outputs"""
    FILESYSTEM = "local"
    MINIO = "minio"