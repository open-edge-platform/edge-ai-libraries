class BaseASR:
   def __init__(self, model_name=..., revision=..., device="cpu"):
       # Abstract Method
       # Load model
       raise NotImplementedError("Must implement in subclass.")

   def transcribe(self, audio_path: str) -> str:
       # Abstract Method
       # Return transcribed text from .wav file
       raise NotImplementedError("Must implement in subclass.")

   def clean_text(self, text: str) -> str:
       """Apply provider-specific text post-processing to an arbitrary string.

       Diarization may split one transcribed segment into per-speaker parts and
       rebuild each part's text from word timings. Those rebuilt strings have not
       passed through the provider's repetition filter, so callers run them
       through this hook. Default is a no-op.

       Args:
           text: raw text to clean.

       Returns:
           The cleaned text.
       """
       return text