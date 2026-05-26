class BaseASR:
   def __init__(self, model_name=..., revision=..., device="cpu"):
       # Abstract Method
       # Load model
       raise NotImplementedError("Must implement in subclass.")

   def transcribe(self, audio_path: str) -> str:
       # Abstract Method
       # Return transcribed text from .wav file
       raise NotImplementedError("Must implement in subclass.")