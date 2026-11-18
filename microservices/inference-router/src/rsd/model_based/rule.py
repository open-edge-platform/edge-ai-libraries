# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Model-based rule: route on the output of a query classifier."""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from threading import Lock
from typing import Any, Hashable, List, Optional, Sequence
from weakref import WeakValueDictionary

from src.config.loader import resolve_workspace_dir
from src.exceptions import ConfigurationError
from src.models import ChatCompletionRequest, ChatCompletionRole
from src.rsd.engine.rule import Rule, _content_text, register_rule
from src.rsd.model_based.base import QueryClassifier
from src.rsd.model_based.registry import ClassifierRegistry, get_registry
from src.rsd.model_based.settings import (
    DEFAULT_VERSION,
    HARD_THRESHOLD,
    KNOWN_BACKBONES,
    MAX_CLASSES,
    build_classifier,
    default_backbone,
    multiclass_classifier_config,
    resolve_ov_model_path,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model-based rule
# ---------------------------------------------------------------------------

class ModelBasedRule(Rule[int]):
    """Model-based routing rule backed by a query classifier.

    Returns the index of the class the classifier decided on -- the routing zone
    -- or ``-1`` when it abstains. With no parameters, the rule uses the
    packaged ``v1`` soft classifier version. With ``prompt_file`` it uses a
    hard-prompt classifier over the user's own categories.

    Args:
        model: Known backbone key. Omit to use ``IR_BACKBONE`` or the built-in
            default.
        version: Optional ``vN`` or ``default`` `.rcv` reference. Omit it with
            no txt-prompt fields to use ``v1``. The registry validates and
            loads the version during policy activation. It is mutually
            exclusive with the txt-prompt fields.
        labels: Multi-class only, optional: ordered category names; a name's
            position is its zone. Omit it to take the categories from the
            strategy's ``provider_selector.label`` (the usual case): each
            provider label there is a category, and the rule returns that
            label's own key, so the selector's keys need not be ``0..N-1``. Set
            it when categories should be named differently from the provider
            labels (e.g. two categories routed to one label).
            Each category is mapped to an internal single-token code (A, B, ...)
            and the answer key is appended to the prompt, so users never deal
            with codes. Requires ``prompt_file``.
        prompt_file: Multi-class: the user's classifier prompt, describing each
            category by its name. Relative paths resolve against the workspace
            directory. Read when the classifier is loaded.
        threshold: Multi-class only: confidence floor -- below it the most
            likely class is not trusted and the rule returns ``-1`` (default
            0.7). The user's prompt has no version to carry it, so it lives in
            the strategy.
        classifier: Optional pre-built classifier (implementing the
            ``QueryClassifier`` protocol); the injection seam for tests. When
            omitted, the OpenVINO classifier is loaded when the active policy is
            preloaded (:meth:`DecisionEngine.preload_classifiers`) or on first
            evaluation -- never at construction, because building a
            ``DecisionEngine`` instantiates the rules of every strategy, active
            or not.

    Raises:
        ConfigurationError: On invalid parameters (checked at construction,
            without loading anything).
    """

    blocking_eval = True

    # Classifier cache shared across instances, keyed by what the classifier is
    # built from. Weak values: an engine rebuild reuses a classifier the current
    # engine still holds, but once no engine references it the classifier (and
    # its backbone runtime) is released instead of lingering in the cache.
    _classifier_cache: "WeakValueDictionary[Hashable, QueryClassifier]" = WeakValueDictionary()
    _classifier_cache_lock = Lock()

    def __init__(
        self,
        model: Optional[str] = None,
        version: Optional[str] = None,
        labels: Optional[Sequence[str]] = None,
        prompt_file: str = "",
        threshold: Any = None,
        classifier: Optional[QueryClassifier] = None,
        registry: Optional[ClassifierRegistry] = None,
    ) -> None:
        self._model_explicit = model is not None
        self.model = model or default_backbone()
        if self.model not in KNOWN_BACKBONES:
            raise ConfigurationError(
                f"ModelBasedRule 'model' must be one of {sorted(KNOWN_BACKBONES)}; "
                f"got {self.model!r}."
            )
        if version is not None and (labels is not None or prompt_file or threshold is not None):
            raise ConfigurationError(
                "ModelBasedRule 'version' is mutually exclusive with "
                "'labels', 'prompt_file', and 'threshold'."
            )
        if version is not None and not isinstance(version, str):
            raise ConfigurationError("ModelBasedRule 'version' must be a string.")
        if version is not None and version != "default" and not re.fullmatch(
            r"v[1-9][0-9]*", version
        ):
            raise ConfigurationError(
                "ModelBasedRule 'version' must be 'default' or vN."
            )
        self.version = (
            DEFAULT_VERSION
            if version is None and labels is None and not prompt_file and threshold is None
            else version
        )
        self.labels: List[str] = self._normalize_labels(labels)
        self.prompt_file = prompt_file
        if self.labels and not prompt_file:
            raise ConfigurationError(
                "ModelBasedRule: 'labels' needs 'prompt_file' (multi-class); omit both "
                "for the packaged soft classifier."
            )
        if threshold is not None and not prompt_file:
            raise ConfigurationError(
                "ModelBasedRule: 'threshold' applies only with 'prompt_file' "
                "(multi-class); a classifier version carries its own threshold."
            )
        self.threshold = self._normalize_threshold(threshold)
        self.classifier = classifier
        self._classifier_initialized = classifier is not None
        self._classifier_load_lock = Lock()
        self._detached = False  # an unload_first swap detached us until the swap rebinds
        # Selector key of each category when the categories come from
        # provider_selector.label; None when the zone is the category's position.
        self._zone_keys: Optional[List[int]] = None
        self.registry = registry or get_registry()

    @property
    def multiclass(self) -> bool:
        return bool(self.prompt_file)

    def configure_from_selector(self, provider_selector: Any, strategy_name: str) -> None:
        """Take the categories from ``provider_selector.label`` when ``labels`` is omitted.

        Called once the owning strategy is built. Every provider label in the
        selector is a category (in key order), and :meth:`evaluate` returns the
        decided category's key -- so the selector reads like for any other rule,
        whatever its keys are. The labels must be distinct.
        """
        if not self.multiclass or self.labels:
            return
        selector = provider_selector.label
        if not isinstance(selector, dict):
            raise ConfigurationError(
                f"Strategy '{strategy_name}': a multi-class ModelBasedRule without 'labels' "
                "takes its categories from provider_selector.label, which must then map "
                f"zones to provider labels; got {selector!r}. "
                "Set 'labels' to name the categories explicitly."
            )
        keys = sorted(selector)
        negative = [key for key in keys if isinstance(key, int) and key < 0]
        if negative:
            raise ConfigurationError(
                f"Strategy '{strategy_name}': provider_selector.label must not use negative "
                f"keys {negative}: -1 is the router's 'no match' sentinel, so those "
                "categories could never be routed to. Use keys from 0 up."
            )
        try:
            self.labels = self._normalize_labels([selector[key] for key in keys])
        except ConfigurationError as exc:
            raise ConfigurationError(
                f"Strategy '{strategy_name}': categories taken from provider_selector.label: "
                f"{exc} Set 'labels' to name the categories explicitly."
            ) from exc
        self._zone_keys = keys

    @property
    def registry_requirement(self) -> Optional[tuple[str, str]]:
        """Classifier version requirement, or ``None`` for a txt-prompt rule."""
        return (self.model, self.version) if self.version is not None else None

    def bind_classifier(self, classifier: Optional[QueryClassifier]) -> None:
        """Publish a fully initialized classifier prepared during reconciliation."""
        with self._classifier_load_lock:
            self.classifier = classifier
            self._classifier_initialized = classifier is not None
            self._detached = False

    def release_classifier(self) -> None:
        """Detach the classifier for an unload_first swap (registry use).

        The rule answers -1 until the swap rebinds it -- it deliberately does
        not pull the old version back out of the registry, so the released
        runtime can actually be freed instead of being pinned again.
        """
        with self._classifier_load_lock:
            self.classifier = None
            self._classifier_initialized = False
            self._detached = True

    def ensure_classifier(self) -> Optional[QueryClassifier]:
        """Return the classifier, loading it on first use.

        A build failure (no model, missing prompt file, ...) leaves the rule
        inert (``classifier is None``, so :meth:`evaluate` returns ``-1``)
        instead of failing startup: a deployment without the model can still
        boot. The attempt is made once.
        """
        if self._classifier_initialized:
            return self.classifier
        with self._classifier_load_lock:
            if not self._classifier_initialized:
                try:
                    if self.version is not None:
                        self.classifier = self.registry.effective(
                            self.model, self.version
                        ).classifier
                    else:
                        self.classifier = self._build_multiclass_classifier()
                except Exception as exc:  # noqa: BLE001 - degrade gracefully
                    logger.warning(
                        "ModelBasedRule disabled: could not load the OpenVINO "
                        "classifier (%s). Set IR_OV_MODEL to a valid model directory%s "
                        "to enable model-based routing.",
                        exc,
                        " and mount the prompt file" if self.multiclass else "",
                    )
                self._classifier_initialized = True
            return self.classifier

    def evaluate(self, request: ChatCompletionRequest) -> int:
        text = self._last_user_text(request)
        # No user text to judge: skip the (wasted) forward pass; defer to fallback.
        if not text.strip():
            return -1
        if self.version is not None and self.classifier is None:
            if self._detached:
                return -1  # an unload_first swap detached us; the swap rebinds
            loaded = self.registry.loaded(self.model, self.version)
            if loaded is not None and loaded.classifier is not None:
                self.bind_classifier(loaded.classifier)
            else:
                self.registry.trigger(self.model, self.version)
                return -1
        classifier = self.ensure_classifier()
        if classifier is None:
            return -1
        result = classifier.classify(text)
        # The classifier already applied the decision (threshold included);
        # index None means it abstained. The rule keeps no threshold of its own.
        # Categories taken from provider_selector.label answer with their key there.
        if result.index is None:
            return -1
        return self._zone_keys[result.index] if self._zone_keys else result.index

    @staticmethod
    def _last_user_text(request: ChatCompletionRequest) -> str:
        """Return the text to classify: the last user message, flattened."""
        for msg in reversed(request.messages):
            if msg.role == ChatCompletionRole.USER and msg.content:
                return _content_text(msg.content)
        return ""

    # -- parameters ------------------------------------------------------

    @staticmethod
    def _normalize_labels(labels: Optional[Sequence[str]]) -> List[str]:
        if labels is None:
            return []
        if isinstance(labels, str) or not all(
            isinstance(label, str) and label.strip() for label in labels
        ):
            raise ConfigurationError("ModelBasedRule 'labels' must be a list of non-empty strings.")
        labels = [label.strip() for label in labels]
        if not 2 <= len(labels) <= MAX_CLASSES:
            raise ConfigurationError(
                f"ModelBasedRule supports 2-{MAX_CLASSES} labels; got {len(labels)}."
            )
        if len(set(labels)) != len(labels):
            raise ConfigurationError(f"ModelBasedRule 'labels' must be distinct: {labels}")
        return labels

    @staticmethod
    def _normalize_threshold(threshold: Any) -> float:
        if threshold is None:
            return HARD_THRESHOLD
        if isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
            value = float(threshold)
            if math.isfinite(value) and 0 <= value <= 1:
                return value
        raise ConfigurationError(
            "ModelBasedRule 'threshold' must be a finite number between 0 and 1."
        )

    # -- classifier building ------------------------------------------------

    @classmethod
    def _cached(cls, key: Hashable, build) -> QueryClassifier:
        """Return the live classifier for ``key``, building it once."""
        with cls._classifier_cache_lock:
            cached = cls._classifier_cache.get(key)
            if cached is not None:
                return cached
            classifier = build()
            cls._classifier_cache[key] = classifier
            return classifier

    def _build_multiclass_classifier(self) -> QueryClassifier:
        """The OV classifier over ``labels`` with the user's prompt plus the answer key."""
        if not self.labels:
            raise ConfigurationError(
                "no categories: set 'labels' or use the rule in a strategy whose "
                "provider_selector.label maps zones to provider labels"
            )
        model_path = self._model_path()
        prompt = Path(self._resolve_prompt_file(self.prompt_file)).read_text(encoding="utf-8")
        cfg = multiclass_classifier_config(model_path, self.labels, prompt, self.threshold)
        key = ("multiclass", model_path, cfg.system_prompt, tuple(self.labels), self.threshold)
        return self._cached(key, lambda: build_classifier(cfg))

    @staticmethod
    def _resolve_prompt_file(prompt_file: str) -> str:
        """Resolve ``prompt_file``; relative paths are under the workspace directory."""
        path = Path(prompt_file).expanduser()
        if not path.is_absolute():
            path = resolve_workspace_dir() / path
        if not path.is_file():
            raise ConfigurationError(
                f"ModelBasedRule prompt_file not found: {path}. "
                "Mount the multi-class classifier prompt and set 'prompt_file'."
            )
        return str(path)

    @classmethod
    def _resolve_ov_model_path(cls, backbone: Optional[str] = None) -> str:
        """Resolve the OpenVINO classifier model directory.

        See :func:`src.rsd.model_based.settings.resolve_ov_model_path`
        (``IR_OV_MODEL_<BACKBONE>``, with ``IR_OV_MODEL`` for the default
        backbone).

        Raises:
            ConfigurationError: If no path is set or it does not exist. Caught by
                :meth:`ensure_classifier`, which logs a warning and leaves the
                rule inert rather than failing startup.
        """
        return resolve_ov_model_path(backbone)

    def _model_path(self) -> str:
        if self._model_explicit:
            return self._resolve_ov_model_path(self.model)
        return self._resolve_ov_model_path()


register_rule(ModelBasedRule)
