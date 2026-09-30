"""OpenVINO (optimum-intel) implementation of :class:`QueryClassifier`.

For each query we run a single forward pass and read the logits at the final
position for the candidate label tokens (E / H), softmax over just those, and
pick the argmax.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from .base import ClassifyResult

logger = logging.getLogger(__name__)


class OVQwenClassifier:
    """E/H intelligent query classifier backed by a Qwen3.5 OpenVINO IR model.

    Args:
        ov_model: Path to the OpenVINO IR directory (``openvino_model.xml/.bin``).
        hf_model: Path to a HuggingFace dir for the tokenizer + chat template
            (often the same dir as ``ov_model``).
        system_prompt: Fallback classifier system prompt.
        system_prompts: Optional language-specific prompts, keyed by ``zh`` and ``en``.
        device: OpenVINO device string, e.g. ``"CPU"`` or ``"GPU.1"``.
        wrap: Prefix wrapped around the user query, e.g. ``"任务："``.
        wraps: Optional language-specific query prefixes, keyed by ``zh`` and ``en``.
        labels: Candidate single-token labels, default ``["E", "H"]``.
        cache_size: Max entries in the per-text LRU cache (0 disables caching).
    """

    def __init__(
        self,
        ov_model: str,
        hf_model: str,
        system_prompt: str,
        system_prompts: Optional[Dict[str, str]] = None,
        device: str = "CPU",
        wrap: str = "任务：",
        wraps: Optional[Dict[str, str]] = None,
        labels: Optional[List[str]] = None,
        cache_size: int = 256,
    ) -> None:
        self.ov_model = ov_model
        self.hf_model = hf_model
        self.system_prompt = system_prompt
        self.system_prompts = dict(system_prompts or {})
        self.device = device
        self.wrap = wrap
        self.wraps = dict(wraps or {})
        self.labels = list(labels) if labels else ["E", "H"]
        self.cache_size = cache_size
        self._cache: "OrderedDict[Tuple[str, str], ClassifyResult]" = OrderedDict()

        self._tok = None
        self._model = None
        self._label_ids: Dict[str, int] = {}
        self._load()  # fail-fast + warm up

    # -- model loading ----------------------------------------------------

    def _resolve_device(self, device: str) -> str:
        """Fall back to CPU when a requested GPU isn't actually available.
        """

        if not device or not device.upper().startswith("GPU"):
            return device
        try:
            from openvino import Core

            available = Core().available_devices
        except Exception as exc:
            logger.warning(
                "Could not enumerate OpenVINO devices (%s); trying %r as requested",
                exc,
                device,
            )
            return device

        available_ok = device in available or (
            "." not in device and any(d.split(".", 1)[0] == "GPU" for d in available)
        )
        if available_ok:
            return device

        logger.warning(
            "Requested device %r not available (have %s); falling back to CPU",
            device,
            available,
        )
        return "CPU"

    def _load(self) -> None:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ImportError(
                "OVQwenClassifier needs the OpenVINO runtime deps "
                "(openvino, optimum-intel, transformers, torch); they ship "
                "with inference-router's dependencies — reinstall the project."
            ) from exc

        from optimum.intel import OVModelForVisualCausalLM as OVModel

        self.device = self._resolve_device(self.device)

        self._tok = AutoTokenizer.from_pretrained(self.hf_model)
        self._model = OVModel.from_pretrained(self.ov_model, device=self.device)

        # Resolve one token id per label; a label that isn't single-token is unusable.
        for c in self.labels:
            ids = self._tok.encode(c, add_special_tokens=False)
            if len(ids) == 1:
                self._label_ids[c] = ids[0]
        missing = [c for c in self.labels if c not in self._label_ids]
        if missing:
            raise ValueError(
                f"Label(s) {missing} are not single tokens for this tokenizer; "
                "pick single-token labels (E/H are single tokens for Qwen)."
            )

    # -- inference --------------------------------------------------------

    @staticmethod
    def _request_language(text: str) -> str:
        return "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in text) else "en"

    def _system_prompt_for(self, text: str) -> tuple[str, str]:
        language = self._request_language(text)
        return language, self.system_prompts.get(language, self.system_prompt)

    def _wrap_for(self, language: str) -> str:
        return self.wraps.get(language, self.wrap)

    def _render(self, text: str) -> str:
        language, system_prompt = self._system_prompt_for(text)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{self._wrap_for(language)}{text}"},
        ]
        return self._tok.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

    def classify(self, text: str) -> ClassifyResult:
        language, _ = self._system_prompt_for(text)
        cache_key = (language, text)
        if self.cache_size and cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        import torch

        prompt = self._render(text)
        inp = self._tok(prompt, return_tensors="pt")
        if "mm_token_type_ids" not in inp:
            token_type_ids = torch.zeros_like(inp["input_ids"])
            inp["mm_token_type_ids"] = token_type_ids
            inp.setdefault("token_type_ids", token_type_ids)
            inp.setdefault(
                "position_ids",
                torch.arange(inp["input_ids"].shape[1]).unsqueeze(0),
            )
        with torch.no_grad():
            out = self._model(**inp)
        logits = out.logits[0, -1]

        label_logits = torch.tensor([logits[self._label_ids[c]].item() for c in self.labels])
        probs = torch.softmax(label_logits, dim=0)
        scores = {c: float(probs[i]) for i, c in enumerate(self.labels)}
        label = max(scores, key=scores.get)
        result = ClassifyResult(label=label, confidence=scores[label], scores=scores)

        if self.cache_size:
            self._cache[cache_key] = result
            self._cache.move_to_end(cache_key)
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return result
