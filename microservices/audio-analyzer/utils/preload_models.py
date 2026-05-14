from components.asr_component import ASRComponent
from utils.config_loader import config

def preload_models():
    # Preload default models
    ASRComponent(session_id="startup", provider=config.models.asr.provider, model_name=config.models.asr.name,device=config.models.asr.device)
