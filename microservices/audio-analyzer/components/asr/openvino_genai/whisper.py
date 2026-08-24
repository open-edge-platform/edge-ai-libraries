from components.asr.base_asr import BaseASR
import soundfile as sf
import librosa, time
import threading
import openvino_genai as ov_genai
import logging
from utils.ensure_model import get_asr_model_path

logger = logging.getLogger(__name__)

# openvino_genai's WhisperPipeline wraps native OpenVINO infer requests that
# are not safe to reuse concurrently: parallel calls to generate() on the
# same pipeline instance raise "RuntimeError: Infer Request is busy".
# ASRComponent shares a single Whisper instance (class-level singleton)
# across all HTTP requests, so this lock serialises generate() calls —
# mirroring the fix applied to the openai-whisper backend.
_TRANSCRIBE_LOCK = threading.Lock()

class Whisper(BaseASR):
   def __init__(self, model_name="whisper-small", device="CPU", revision=None):
        logger.info(f"Loading Model: model name={model_name}, device={device}")
        self.model_path = get_asr_model_path()
        self.model = ov_genai.WhisperPipeline( self.model_path, device=device)
 
   def transcribe(self, audio_path: str, temperature: float = 0.0, language: str | None = None) -> dict:
        audio, sr = self._load_wav_mono_16k(audio_path)
        gen_kwargs = {"return_timestamps": True}
        if language:
            gen_kwargs["language"] = language if language.startswith("<|") else f"<|{language}|>"
        with _TRANSCRIBE_LOCK:
            result = self.model.generate(audio, **gen_kwargs)
        segments = []
        if hasattr(result, "chunks") and result.chunks is not None:
            for seg in result.chunks:
                segments.append({
                    "start": float(seg.start_ts),
                    "end": float(seg.end_ts),
                    "text": seg.text
                })

        return {
            "text": result.texts[0],
            "segments": segments
        }
   
   def _load_wav_mono_16k(self, path):
    # load with soundfile and resample to 16 kHz if necessary
    audio, sr = sf.read(path, dtype='float32')
    if sr != 16000:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
        sr = 16000
    # if stereo, average channels
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, sr