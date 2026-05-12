from components.asr.base_asr import BaseASR
import soundfile as sf
import librosa, time
import numpy as np
import json
import whisper
from openvino import Core
import logging
from utils.ensure_model import get_asr_model_path

logger = logging.getLogger(__name__)  
 
class Whisper(BaseASR):
    def __init__(self, model_name="whisper-small", device="CPU", revision=None):
        logger.info(f"Loading Model: model name={model_name}, device={device}")
        
        self.model_name = model_name
        self.model_path = get_asr_model_path()
        self.device = device

        # --- Tokenizer ---
        self.tokenizer = whisper.tokenizer.get_tokenizer(multilingual=True)

        # --- Config ---
        with open(f"{self.model_path}/config.json", "r") as f:
            config = json.load(f)
        self._tok = lambda s: self.tokenizer.encode(
            s,
            allowed_special={s}
        )[0]

        self.SOT = config["decoder_start_token_id"]
        self.EOT = config["eos_token_id"]
        self.TIMESTAMP_BEGIN = self.tokenizer.timestamp_begin

        # --- OpenVINO Models ---
        core = Core()
        
        self.encoder = core.compile_model(
            f"{self.model_path}/openvino_encoder_model.xml",
            self.device
        )
        self.decoder = core.compile_model(
            f"{self.model_path}/openvino_decoder_model.xml",
            self.device
        )

        logger.info("OpenVINO Whisper models loaded successfully")
 
    def transcribe(self, audio_path: str, temperature: float = 0.0, language: str | None = None) -> dict:
        
        # --- Load audio ---
        audio, sr = self._load_wav_mono_16k(audio_path)

        # --- Whisper preprocessing ---
        audio = whisper.pad_or_trim(audio)
        audio = audio.astype(np.float32)
        mel = whisper.log_mel_spectrogram(audio).numpy()[None, :]

        # --- Encoder ---
        encoder_output = self.encoder([mel])[0]

        # --- Decode ---
        tokens = [
            self.SOT,
            self._tok(f"<|{language or 'en'}|>"),
            self._tok("<|transcribe|>"),
            self.TIMESTAMP_BEGIN
        ]

        for step in range(448):
            inp = np.array(tokens, dtype=np.int64)[None, :]
            seq_len = inp.shape[1]

            cache_position = np.arange(seq_len, dtype=np.int64)
            beam_idx = np.zeros((1,), dtype=np.int32)

            inputs_map = {
                "input_ids": inp,
                "encoder_hidden_states": encoder_output,
                "cache_position": cache_position,
                "beam_idx": beam_idx,
            }

            req = self.decoder.create_infer_request()
            req.infer(inputs_map)

            logits = req.get_output_tensor(0).data
            next_logits = logits[0, -1] if logits.ndim == 3 else logits[-1]

            next_token = int(np.argmax(next_logits))
            tokens.append(next_token)

            if next_token == self.EOT:
                break

        # --- Clean output ---
        return self._clean_and_segment(tokens)

    def _clean_and_segment(self, tokens):
        segments = []
        clean_tokens = []
        current_text = ""
        seg_start = None

        for tok in tokens:
            # Timestamp token
            if tok >= self.TIMESTAMP_BEGIN:
                t = (tok - self.TIMESTAMP_BEGIN) * 0.02

                if seg_start is None:
                    seg_start = t
                else:
                    if current_text.strip():
                        segments.append({
                            "start": round(seg_start, 2),
                            "end": round(t, 2),
                            "text": current_text.strip()
                        })
                    seg_start = None
                    current_text = ""
                continue

            txt = self.tokenizer.decode([tok]).strip()
            CONTROL_TOKENS = {
            "<|startoftranscript|>",
            "<|endoftext|>",
            "<|notimestamps|>",
            "<|nospeech|>",
            "<|transcribe|>",
            "<|translate|>",
            "<|en|>",
            "<|zh|>",
            "<|de|>",
            "<|fr|>",
            "<|es|>",
            "<|ja|>",
        }

            # Drop only known control tokens
            if txt in CONTROL_TOKENS:
                continue

            clean_tokens.append(tok)
            current_text += self.tokenizer.decode([tok])

        if seg_start is not None and current_text.strip():
            segments.append({
                "start": round(seg_start, 2),
                "end": round(seg_start + 1.0, 2),
                "text": current_text.strip()
            })

        final_text = self.tokenizer.decode(clean_tokens).strip()

        return {
            "text": final_text,
            "segments": segments
        }
   
    def _load_wav_mono_16k(self, path):
        audio, sr = sf.read(path, dtype='float32')
        if sr != 16000:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
            sr = 16000
        # If stereo, average channels
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio, sr