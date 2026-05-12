import os
import logging
import numpy as np
from typing import Dict, Any

logger = logging.getLogger(__name__)

LABEL_MAP = {
    "neu": "neutral",
    "hap": "happy",
    "sad": "sad",
    "ang": "angry",
    # SpeechBrain uses full names too; keep both
    "neutral":  "neutral",
    "happy":    "happy",
    "sad":      "sad",
    "angry":    "angry",
}

SAMPLE_RATE = 16000
PYTORCH_LABEL_ORDER = ["neutral", "angry", "happy", "sad"]


class SpeechBrainSentiment:
    """
    Voice sentiment using speechbrain/emotion-recognition-wav2vec2-IEMOCAP.

    Two inference paths (config.sentiment.provider):
      - pytorch  : direct SpeechBrain inference (simpler, no export needed)
      - openvino : OV IR exported via optimum-intel (faster on CPU/GPU at edge)
    """

    def __init__(self, model_path: str, device: str = "CPU", provider: str = "openvino"):
        self.provider = provider.lower()
        self.device = device.upper()
        self.model_path = model_path

        if self.provider == "pytorch":
            self._load_pytorch(model_path)
        elif self.provider == "openvino":
            self._load_openvino(model_path)
        else:
            raise ValueError(f"Unknown sentiment provider: {provider!r}. Use 'pytorch' or 'openvino'.")

    # ── pytorch ──────────────────────────────────────────────────────────────

    def _load_pytorch(self, model_path: str) -> None:
        try:
            from speechbrain.inference.interfaces import foreign_class
        except ImportError as exc:
            raise RuntimeError(
                "speechbrain is not installed. Run: pip install speechbrain"
            ) from exc

        logger.info(f"Loading SpeechBrain emotion model (pytorch) from {model_path}")
        run_device = "cuda" if self.device == "GPU" else "cpu"
        self._classifier = foreign_class(
            source=model_path,
            savedir=model_path,
            pymodule_file="custom_interface.py",
            classname="CustomEncoderWav2vec2Classifier",
            run_opts={"device": run_device},
        )
        self._feature_extractor = None  # SpeechBrain handles its own features
        self._ov_model = None

    # ── openvino ─────────────────────────────────────────────────────────────

    def _load_openvino(self, model_path: str) -> None:
        try:
            import openvino as ov
        except ImportError as exc:
            raise RuntimeError(
                "openvino is required for OV sentiment inference."
            ) from exc

        xml_path = os.path.join(model_path, "openvino_model.xml")
        if not os.path.isfile(xml_path):
            raise FileNotFoundError(
                f"OpenVINO IR not found at {xml_path}. "
                "Run ensure_model() to export the sentiment model first."
            )

        logger.info(f"Compiling OV sentiment model from {xml_path} on {self.device}")
        core = ov.Core()
        model = core.read_model(xml_path)
        self._ov_model = core.compile_model(model, self.device)
        self._ov_input_name = self._ov_model.input(0).get_any_name()
        self._ov_label_names = self._load_label_names(model_path)
        self._classifier = None

    def _load_label_names(self, model_path: str) -> list[str]:
        label_encoder_path = os.path.join(model_path, "label_encoder.txt")
        if os.path.isfile(label_encoder_path):
            labels_by_index: dict[int, str] = {}
            with open(label_encoder_path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("="):
                        continue
                    if "=>" not in line:
                        continue
                    raw_label, raw_index = [part.strip() for part in line.split("=>", 1)]
                    if not raw_label.startswith("'"):
                        continue
                    label = raw_label.strip("'")
                    mapped_label = LABEL_MAP.get(label)
                    if mapped_label is None:
                        continue
                    try:
                        index = int(raw_index)
                    except ValueError:
                        continue
                    labels_by_index[index] = mapped_label
            if labels_by_index:
                return [labels_by_index[index] for index in sorted(labels_by_index)]
        return PYTORCH_LABEL_ORDER

    # ── inference ─────────────────────────────────────────────────────────────

    def predict(self, audio_path: str) -> Dict[str, Any]:
        """
        Returns:
            {
                "label":  "neutral" | "happy" | "sad" | "angry",
                "score":  float (0–1),
                "scores": {"neutral": float, "happy": float, "sad": float, "angry": float}
            }
        """
        if self.provider == "pytorch":
            return self._predict_pytorch(audio_path)
        return self._predict_openvino(audio_path)

    def _load_audio(self, audio_path: str) -> np.ndarray:
        try:
            import soundfile as sf
            audio, sr = sf.read(audio_path, dtype="float32")
        except Exception:
            import wave, array as arr
            with wave.open(audio_path) as wf:
                raw = wf.readframes(wf.getnframes())
                samples = arr.array("h", raw)
                audio = np.array(samples, dtype=np.float32) / 32768.0
                sr = wf.getframerate()
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != SAMPLE_RATE:
            # Simple linear resample via numpy (avoids scipy dependency)
            target_len = int(len(audio) * SAMPLE_RATE / sr)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, target_len),
                np.arange(len(audio)),
                audio,
            )
        return audio

    def _predict_pytorch(self, audio_path: str) -> Dict[str, Any]:
        out_prob, _, _, labels = self._classifier.classify_file(audio_path)
        probs = out_prob.squeeze().tolist()
        if not isinstance(probs, list):
            probs = [float(probs)]
        scores = {
            PYTORCH_LABEL_ORDER[index]: round(float(probability), 4)
            for index, probability in enumerate(probs)
            if index < len(PYTORCH_LABEL_ORDER)
        }
        predicted_label = str(labels[0]) if labels else max(scores, key=scores.get)
        best = LABEL_MAP.get(predicted_label, predicted_label)
        if best not in scores and scores:
            best = max(scores, key=scores.get)
        return {"label": best, "score": round(scores[best], 4), "scores": {k: round(v, 4) for k, v in scores.items()}}

    def _predict_openvino(self, audio_path: str) -> Dict[str, Any]:
        audio = self._load_audio(audio_path)
        result = self._ov_model({self._ov_input_name: audio[None, :].astype(np.float32)})
        probs = np.array(list(result.values())[0][0], dtype=np.float32)
        if probs.ndim != 1:
            probs = probs.reshape(-1)
        total = float(probs.sum())
        if total > 0:
            probs = probs / total
        label_names = self._ov_label_names
        scores = {
            label_names[i] if i < len(label_names) else f"label_{i}": round(float(probs[i]), 4)
            for i in range(len(probs))
        }
        best = max(scores, key=scores.get)
        return {"label": best, "score": round(scores[best], 4), "scores": scores}
