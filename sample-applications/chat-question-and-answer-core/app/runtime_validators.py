from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # To avoid circular imports
    from config import Settings

class BackendValidator:
    def __init__(self, settings: "Settings"):
        self.settings = settings

    def validate(self):
        raise NotImplementedError("Subclasses must implement this method.")


class OpenVINOValidator(BackendValidator):
    def validate(self):
        self.settings.MODEL_RUNTIME = "openvino"
        if not self.settings.HF_ACCESS_TOKEN:
            raise ValueError("HF_ACCESS_TOKEN must not be empty for 'openvino' backend.")

        for model_name in ["EMBEDDING_MODEL_ID", "RERANKER_MODEL_ID", "LLM_MODEL_ID"]:
            if not getattr(self.settings, model_name):
                raise ValueError(f"{model_name} must not be empty for 'openvino' backend.")

        self.settings._ENABLE_RERANK = True


class OllamaValidator(BackendValidator):
    def validate(self):
        self.settings.MODEL_RUNTIME = "ollama"
        invalid_devices = [
            attr for attr in ["EMBEDDING_DEVICE", "RERANKER_DEVICE", "LLM_DEVICE"]
            if getattr(self.settings, attr) != "CPU"
        ]
        if invalid_devices:
            raise ValueError(
                f"When MODEL_RUNTIME is 'ollama', the following devices must be set to 'CPU': {', '.join(invalid_devices)}"
            )

        if self.settings.RERANKER_MODEL_ID:
            print("WARNING - RERANKER_MODEL_ID is ignored for 'ollama'. Setting it to empty.")
            self.settings.RERANKER_MODEL_ID = ""
        else:
            print("INFO - Reranker model not supported for 'ollama'.")

        for model_name in ["EMBEDDING_MODEL_ID", "LLM_MODEL_ID"]:
            if not getattr(self.settings, model_name):
                raise ValueError(f"{model_name} must not be empty for 'ollama' backend.")

        self.settings._ENABLE_RERANK = False
