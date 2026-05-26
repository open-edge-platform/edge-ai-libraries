import logging
from typing import List, Dict, Any

from utils.config_loader import config

logger = logging.getLogger(__name__)

SENTIMENT_LABELS = ["neutral", "happy", "sad", "angry"]


class SentimentComponent:
    """
    Singleton voice-sentiment component.
    Runs speechbrain/emotion-recognition-wav2vec2-IEMOCAP per audio chunk,
    then aggregates per-chunk results into a session-level summary.
    """

    _model = None
    _model_key = None

    def __init__(self):
        cfg = config.sentiment
        model_name = cfg.model
        device = cfg.device
        provider = cfg.provider
        models_base = cfg.models_base_path

        # Derive local model dir: models/sentiment/<slug>/
        slug = model_name.replace("/", "_")
        model_path = f"{models_base}/sentiment/{slug}"

        key = (model_name, device, provider)
        if SentimentComponent._model is None or SentimentComponent._model_key != key:
            from components.sentiment.speechbrain.sentiment import SpeechBrainSentiment
            SentimentComponent._model = SpeechBrainSentiment(model_path, device, provider)
            SentimentComponent._model_key = key

        self._classifier = SentimentComponent._model
        self._recency_weight = getattr(cfg, "recency_weight", 0.7)
        self._peak_label = getattr(cfg, "peak_label", "angry")

    # ── per-chunk inference ───────────────────────────────────────────────────

    def analyze(self, audio_path: str) -> Dict[str, Any]:
        """Run sentiment on a single audio chunk."""
        try:
            return self._classifier.predict(audio_path)
        except Exception as exc:
            logger.warning(f"Sentiment analysis failed for {audio_path}: {exc}")
            return {"label": "neutral", "score": 0.0, "scores": {}}

    # ── session aggregation ───────────────────────────────────────────────────

    @staticmethod
    def aggregate(chunk_results: List[Dict[str, Any]],
                  recency_weight: float = 0.7,
                  peak_label: str = "angry") -> Dict[str, Any]:
        """
        Aggregate per-chunk sentiment results into a session summary.

        Args:
            chunk_results: list of {"label", "score", "scores"} dicts, one per chunk
            recency_weight: 0.0 = equal weights, 1.0 = last chunk only
            peak_label: label to watch for escalation detection

        Returns:
            {
                "dominant": str,       # highest recency-weighted label
                "current":  str,       # label from last chunk
                "peak":     str,       # highest-score occurrence of peak_label
                "peak_score": float,
                "trajectory": [str],   # ordered list of per-chunk labels
            }
        """
        if not chunk_results:
            return {
                "dominant": "neutral", "current": "neutral",
                "peak": "neutral", "peak_score": 0.0, "trajectory": [],
            }

        n = len(chunk_results)
        # Recency weights: linear ramp from (1 - recency_weight) to 1.0
        low = 1.0 - recency_weight
        weights = [low + recency_weight * (i / max(n - 1, 1)) for i in range(n)]
        total_w = sum(weights)

        # Weighted score accumulator
        label_scores: Dict[str, float] = {lbl: 0.0 for lbl in SENTIMENT_LABELS}
        for w, result in zip(weights, chunk_results):
            for lbl, sc in result.get("scores", {}).items():
                if lbl in label_scores:
                    label_scores[lbl] += w * sc
        dominant = max(label_scores, key=label_scores.get)

        # Normalise
        label_scores = {k: round(v / total_w, 4) for k, v in label_scores.items()}

        # Peak detection for configured escalation label
        peak_score = 0.0
        for result in chunk_results:
            sc = result.get("scores", {}).get(peak_label, 0.0)
            if sc > peak_score:
                peak_score = sc

        trajectory = [r["label"] for r in chunk_results]

        return {
            "dominant":   dominant,
            "current":    chunk_results[-1]["label"],
            "peak":       peak_label,
            "peak_score": round(peak_score, 4),
            "trajectory": trajectory,
        }
