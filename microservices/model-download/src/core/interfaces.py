from abc import ABC, abstractmethod
from typing import Optional
from ..api.models import ModelRequest, ModelResult

class ModelDownloadPlugin(ABC):
    @abstractmethod
    def download(self, model: ModelRequest, model_path: str, hf_token: Optional[str] = None) -> ModelResult:
        pass