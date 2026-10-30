# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Classifiers on top of a shared :class:`~.runtime.BackboneRuntime`.

:class:`PromptClassifier` runs one classifier version (a ``.rcv`` bundle, soft
or hard). :class:`OVQwenClassifier` runs a hard prompt given as text (a
multi-class rule's ``prompt_file`` plus its answer key).

Hard prompts:

For each query we render the hard prompt in Qwen's chat template, take the
backbone's post-norm hidden state at the final position and score it with a
C-row head: the lm_head rows of the C answer tokens (the letter codes of a
multi-class rule; :meth:`.runtime.BackboneRuntime.label_rows`).
``h @ rows.T`` equals those tokens' entries in the full vocab logits, without the
vocab-sized matmul. Softmax over just those C logits, then
:func:`.base.decide`: the most likely class, unless it is below the
threshold.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import numpy as np

from .base import ClassifyResult, QueryClassifier, decide, zone_probs
from .bundle import KIND_SOFT, ClassifierBundle
from .runtime import BackboneRuntime, get_runtime
from .vocab_tokens import VocabTokenPatch, token_patch

logger = logging.getLogger(__name__)


def label_scores(label_logits: np.ndarray, labels: List[str]) -> Dict[str, float]:
    """Softmax over the candidate label logits."""
    logits = np.asarray(label_logits, dtype=np.float64)
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()
    return {c: float(probs[i]) for i, c in enumerate(labels)}


def qwen_chat(system_prompt: str, user: str) -> str:
    """Hand-built Qwen chat template: system + user + empty-thinking generation prefix.

    Reproduces ``apply_chat_template(..., add_generation_prompt=True,
    enable_thinking=False)`` for this fixed two-message shape; verified to
    yield token ids identical to the HuggingFace tokenizer.
    """
    blocks = []
    if system_prompt:
        blocks.append(f"<|im_start|>system\n{system_prompt}<|im_end|>\n")
    blocks.append(f"<|im_start|>user\n{user}<|im_end|>\n")
    blocks.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    return "".join(blocks)


def llama3_chat(system_prompt: str, user: str) -> str:
    """Hand-built Llama-3 chat template for the same two-message shape
    (system + user + open assistant turn)."""
    blocks = ["<|begin_of_text|>"]
    if system_prompt:
        blocks.append(
            f"<|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|>"
        )
    blocks.append(f"<|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>")
    blocks.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
    return "".join(blocks)


def render_chat(style: str, system_prompt: str, user: str) -> str:
    """Render a hard prompt in the backbone's chat template."""
    if style == "llama3":
        return llama3_chat(system_prompt, user)
    return qwen_chat(system_prompt, user)


def hard_result(
    scores: Dict[str, float],
    threshold: float,
    raw: Optional[Dict[str, float]] = None,
) -> ClassifyResult:
    """Turn class probabilities (in class order) into a :class:`ClassifyResult`
    via :func:`.base.decide` (one zone per class)."""
    labels = list(scores)
    probs = [scores[c] for c in labels]
    index = decide(probs, threshold)
    return ClassifyResult(
        label=labels[index] if index is not None else None,
        confidence=max(probs),
        scores=dict(scores),
        index=index,
        threshold=threshold,
        kind="hard",
        raw={"label_logits": dict(raw or {})},
    )


class OVQwenClassifier(QueryClassifier):
    """Hard-prompt query classifier over the given labels, from a text system prompt.

    Implements the :class:`~.base.QueryClassifier` interface, which is what the
    rule and the rest of the router depend on; other classifiers (or test stubs)
    plug in by implementing the same interface.

    Args:
        ov_model: OpenVINO IR directory of the backbone (see :mod:`.runtime` for
            the accepted layouts).
        system_prompt: The classifier system prompt, used for every query; the
            query itself is the user message, unchanged.
        device: OpenVINO device string, e.g. ``"CPU"`` or ``"GPU.1"``.
        labels: Class names, default ``["E", "H"]``; their order is the
            ``index`` (routing zone) of a result.
        label_tokens: The single token the model answers with for each label,
            in the same order; defaults to the labels themselves.
        cache_size: Max entries in the per-text LRU cache (0 disables caching).
            The cache holds class probabilities, not decisions, so the decision
            parameters can change without invalidating it.
        threshold: Abstain when the most likely class is below this
            (see :func:`.base.decide`).
        runtime: Backbone to run on. Defaults to the shared runtime for
            ``(ov_model, device)`` from :func:`.runtime.get_runtime`, so
            classifiers on the same backbone compile it only once; that
            runtime is re-resolved per query, so the classifier moves onto a
            patched runtime compiled later (a token-form version's) and the
            unpatched one is released instead of kept next to it.
    """

    def __init__(
        self,
        ov_model: str,
        system_prompt: str = "",
        device: str = "CPU",
        labels: Optional[List[str]] = None,
        label_tokens: Optional[List[str]] = None,
        cache_size: int = 256,
        threshold: float = 0.7,
        runtime: Optional[BackboneRuntime] = None,
    ) -> None:
        self.ov_model = ov_model
        self.system_prompt = system_prompt
        self.device = device
        self.labels = list(labels) if labels else ["E", "H"]
        self.label_tokens = list(label_tokens) if label_tokens else list(self.labels)
        if len(self.label_tokens) != len(self.labels):
            raise ValueError(f"need one token per label: {self.label_tokens} vs {self.labels}")
        for name, values in (("labels", self.labels), ("label_tokens", self.label_tokens)):
            if len(values) < 2 or len(set(values)) != len(values):
                raise ValueError(f"{name} must be at least two distinct values: {values}")
        self.cache_size = cache_size
        self.threshold = threshold
        # text -> (class probabilities, class logits), keyed by label
        self._cache: "OrderedDict[str, Tuple[Dict[str, float], Dict[str, float]]]" = OrderedDict()

        self._requested_device = device
        self._shared_runtime = runtime is None  # re-resolve via get_runtime per query
        self._runtime = runtime if runtime is not None else get_runtime(ov_model, device)
        self.device = self._runtime.device  # after any GPU -> CPU fallback
        self._label_ids: Dict[str, int] = {}
        self._head = self._build_head()  # fail-fast on non-single-token labels
        self._head64 = self._head.astype(np.float64)  # converted once, like the soft head

    def _build_head(self) -> np.ndarray:
        """The C-row head: lm_head rows of the label tokens, ``[len(labels), H]``."""
        # Resolve one token id per label token; one that isn't a single token
        # is unusable. A tokenizer-level prefix (Llama's BOS) is not part of
        # the code and is stripped before the check.
        for c in self.label_tokens:
            ids = self._runtime.strip_prompt_prefix(self._runtime.encode(c))
            if len(ids) == 1:
                self._label_ids[c] = int(ids[0])
        missing = [c for c in self.label_tokens if c not in self._label_ids]
        if missing:
            raise ValueError(
                f"Label token(s) {missing} are not single tokens for this tokenizer; "
                "pick single-token labels (E/H and A-Z are single tokens for Qwen)."
            )
        return self._runtime.label_rows([self._label_ids[c] for c in self.label_tokens])

    # -- inference --------------------------------------------------------

    def _render(self, text: str) -> str:
        """The system prompt and the query in the backbone's chat template."""
        return render_chat(self._current_runtime().chat_style, self.system_prompt, text)

    def _current_runtime(self) -> BackboneRuntime:
        """The shared runtime to run on now (see ``runtime`` in the class docstring).

        The head rows stay valid on any runtime of the backbone: a patch only
        writes free rows, never the label tokens' rows.
        """
        if self._shared_runtime:
            self._runtime = get_runtime(self.ov_model, self._requested_device)
        return self._runtime

    def _label_logits(self, prompt: str) -> np.ndarray:
        """Label logits ``[len(labels)]`` for a rendered prompt: last hidden @ head rows."""
        rt = self._current_runtime()
        hidden = rt.last_hidden(rt.embed(rt.encode(prompt)))
        return self._head64 @ hidden.astype(np.float64)

    def classify(self, text: str) -> ClassifyResult:
        cache_key = text
        if self.cache_size and cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            scores, raw = self._cache[cache_key]
            return hard_result(scores, self.threshold, raw)

        label_logits = self._label_logits(self._render(text))
        scores = label_scores(label_logits, self.labels)
        raw = {c: float(label_logits[i]) for i, c in enumerate(self.labels)}

        if self.cache_size:
            self._cache[cache_key] = (scores, raw)
            self._cache.move_to_end(cache_key)
            if len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return hard_result(scores, self.threshold, raw)


class PromptClassifier(QueryClassifier):
    """One classifier version (a ``.rcv`` bundle) on a shared backbone runtime.

    Soft and hard versions differ in how the input is built and the head applied:

    * soft (token form) -- plain token ids ``[soft token ids][pad ids x P]
      [query ids]``, the layout the soft prompt was trained with (``P`` masked
      pads, the raw query truncated to ``text_max_tokens``). The runtime's
      embedding table holds the soft rows and its lm_head the class rows, so
      the class logits are the vocabulary logits read at the class token ids
      (:meth:`~.runtime.BackboneRuntime.class_logits`), plus the packed
      ``head_bias`` outside the graph;
    * hard -- the system prompt and the raw query in Qwen's chat template;
      last hidden @ the packed head rows.

    The rest is shared: softmax over the classes -> merge into zones
    (``class_zones``) -> :func:`.base.decide` on the version's ``threshold``.
    The LRU cache holds class probabilities, keyed by text.

    Args:
        bundle: The classifier version.
        runtime: Backbone runtime; its hidden size must match the bundle. A
            soft bundle needs the runtime patched with exactly its vocabulary
            rows (:attr:`~.runtime.BackboneRuntime.token_patch_digest`).
        cache_size: Max cached queries (0 disables caching).
        vocab_patch: The version's :class:`~.vocab_tokens.VocabTokenPatch`, if
            the caller has already built it (the registry has). Computed from
            the bundle when omitted.
    """

    def __init__(
        self,
        bundle: ClassifierBundle,
        runtime: BackboneRuntime,
        cache_size: int = 256,
        vocab_patch: Optional[VocabTokenPatch] = None,
    ) -> None:
        if runtime.hidden_size != bundle.hidden:
            raise ValueError(
                f"version {bundle.version} has hidden {bundle.hidden}, "
                f"the backbone has {runtime.hidden_size}"
            )
        self.bundle = bundle
        self.kind = bundle.kind
        self.version = bundle.version
        self.zone_names = bundle.zone_names
        self.threshold = bundle.threshold
        self.cache_size = cache_size
        self._runtime = runtime
        self._class_zones = bundle.class_zones
        self._head_w = bundle.head_weight.astype(np.float64)  # hard versions
        self._head_b = bundle.head_bias.astype(np.float64)
        self._text_max_tokens = int(bundle.meta["text_max_tokens"])
        self._truncate_left = bundle.meta["truncation_side"] == "left"
        self._cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
        self.token_form = bundle.token_form
        if self.kind == KIND_SOFT and not self.token_form:
            raise ValueError(
                f"soft version {bundle.version} has no vocabulary token ids; "
                "soft versions are token form only"
            )
        if self.token_form:
            patch = vocab_patch if vocab_patch is not None else token_patch(bundle)
            if runtime.token_patch_digest != patch.digest:
                raise ValueError(
                    f"version {bundle.version} is token-form but the backbone runtime "
                    f"({'patched with ' + runtime.token_patch_digest if runtime.token_patch_digest else 'unpatched'}) "  # noqa: E501
                    f"does not hold its vocabulary rows ({patch.digest})"
                )
            self._soft_ids = np.asarray(bundle.soft_token_ids, dtype=np.int64)
        if self.kind == KIND_SOFT:
            self._pad_ids = self._pad_block(bundle)

    @staticmethod
    def _pad_block(bundle: ClassifierBundle) -> np.ndarray:
        """The pad block's token ids, from ``render``."""
        render = bundle.meta["render"]
        if render.get("template") != "raw" or render.get("soft_position", "before") != "before":
            raise ValueError(f"unsupported soft render {render}; expected raw text, soft first")
        padding = render.get("padding", {})
        n_pad = int(padding.get("between_soft_and_query", 0))
        if n_pad and "pad_token_id" not in padding:
            raise ValueError("render.padding needs pad_token_id for the pad block")
        return np.full(n_pad, int(padding.get("pad_token_id", 0)), dtype=np.int64)

    def rebind_runtime(self, runtime: BackboneRuntime) -> None:
        """Run a hard version on another runtime of the same backbone (registry use).

        Only hard versions can move: a soft version needs exactly its patched runtime.
        """
        if self.token_form:
            raise ValueError("a soft version is bound to its patched runtime")
        self._runtime = runtime

    def _query_ids(self, text: str) -> np.ndarray:
        ids = self._runtime.encode(text)
        if len(ids) > self._text_max_tokens:
            n = self._text_max_tokens
            ids = ids[-n:] if self._truncate_left else ids[:n]
        return ids

    def _inputs_soft(self, text: str) -> Tuple[np.ndarray, np.ndarray]:
        ids = self._query_ids(text)
        if len(ids) == 0:
            raise ValueError("cannot classify an empty query")
        # The soft prefix is plain token ids; the runtime's embedding table
        # already holds the trained rows.
        embeds = self._runtime.embed(np.concatenate([self._soft_ids, self._pad_ids, ids]))
        k = len(self._soft_ids)
        mask = np.concatenate(
            [np.ones(k), np.zeros(len(self._pad_ids)), np.ones(len(ids))]
        ).astype(np.int64)
        return embeds, mask

    def _inputs_hard(self, text: str) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        # Hard-prompt queries are not truncated inside the template.
        rt = self._runtime
        return rt.embed(rt.encode(render_chat(rt.chat_style, self.bundle.prompt, text))), None

    def class_probs(self, text: str) -> np.ndarray:
        """Probability of each class (before merging into zones)."""
        embeds, mask = (self._inputs_soft if self.kind == KIND_SOFT else self._inputs_hard)(text)
        if self.token_form:
            # vocabulary logits read at the class token ids, in class order
            logits = self._runtime.class_logits(embeds, mask).astype(np.float64) + self._head_b
        else:
            hidden = self._runtime.last_hidden(embeds, mask).astype(np.float64)
            logits = self._head_w @ hidden + self._head_b
        exp = np.exp(logits - logits.max())
        return exp / exp.sum()

    def classify(self, text: str) -> ClassifyResult:
        if self.cache_size and text in self._cache:
            self._cache.move_to_end(text)
            probs = self._cache[text]
        else:
            probs = self.class_probs(text)
            if self.cache_size:
                self._cache[text] = probs
                if len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
        zones = zone_probs(probs, self._class_zones)
        index = decide(zones, self.threshold)
        return ClassifyResult(
            label=self.zone_names[index] if index is not None else None,
            confidence=float(zones.max()),
            scores={name: float(p) for name, p in zip(self.zone_names, zones)},
            index=index,
            threshold=self.threshold,
            kind=self.kind,
            version=self.version,
            raw={"class_probs": probs.tolist()},
        )
