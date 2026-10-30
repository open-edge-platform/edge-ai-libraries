# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Classifier-version registry and atomic active-policy reconciliation."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

from src.exceptions import ConfigurationError
from src.rsd.model_based.classifier import PromptClassifier
from src.rsd.model_based.format import read_rcv
from src.rsd.model_based.runtime import get_runtime, get_tokenizer
from src.rsd.model_based.settings import (
    DEFAULT_VERSION,
    KNOWN_BACKBONES,
    artifacts_dir,
    default_version_path,
    resolve_ov_model_path,
    swap_mode,
)
from src.rsd.model_based.validate import (
    check_model_name,
    check_tokenizer,
    validate_against_runtime,
)
from src.rsd.model_based.vocab_tokens import VocabTokenPatch, token_patch

logger = logging.getLogger(__name__)

VersionKey = Tuple[str, str]
# Runtime cache key: backbone, device and -- for token-form versions, which
# write their rows into the graph -- the patch digest.
RuntimeKey = Tuple[str, str, Optional[str]]
_VERSION_RE = re.compile(r"v[1-9][0-9]*\Z")
_VERSION_FILE_RE = re.compile(r"(v[1-9][0-9]*)\.rcv\Z")


class ClassifierRegistryError(ConfigurationError):
    """A requested classifier version cannot be loaded safely."""


class ClassifierNotFoundError(ClassifierRegistryError):
    """The requested model is not a known backbone, or the version does not exist."""


@dataclass(frozen=True)
class EffectiveClassifier:
    """Classifier selected for one requested ``(model, version)``."""

    classifier: Optional[Any]
    requested: VersionKey
    effective: Optional[VersionKey]
    status: str
    reason: Optional[str] = None
    origin: Optional[str] = None
    validation: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class ReconcileResult:
    """Result of reconciling the registry with one active policy."""

    bindings: Mapping[VersionKey, EffectiveClassifier]
    loaded: int
    released: int
    elapsed_ms: float


@dataclass(frozen=True)
class VersionCheck:
    """Result of checking one version without publishing it (:meth:`ClassifierRegistry.check`)."""

    bundle: Any
    origin: str  # "package", "artifacts", or "new" for an in-memory bundle
    validation: Mapping[str, Any]
    loaded: bool  # the full L1/L2/L3 + warmup ran (or the version is already serving)
    warmup_ms: Optional[float] = None


@dataclass(frozen=True)
class VersionListing:
    """One version file of a backbone, as :meth:`ClassifierRegistry.versions` lists it."""

    version: str
    origin: str  # "package" or "artifacts"
    bundle: Any  # None when the file cannot be used (see ``error``)
    loaded: bool  # loaded and serving right now
    error: Optional[str] = None


@dataclass(frozen=True)
class _VersionSource:
    canonical_version: str
    path: Path
    origin: str


class ClassifierRegistry:
    """Own loaded versions and runtimes needed by the active policy.

    Two locks: ``_build_lock`` serializes the expensive work (loading, L1/L2/L3,
    warmup, reconciliation) and is held for its whole duration; ``_lock`` guards
    the published state and is only held for a moment. Request threads only
    read published state (:meth:`loaded`), so they never wait for a load. A
    classifier is published to ``_clfs`` only after format validation, L1/L2/L3
    checks and warmup all succeed, so they never observe partial state either.
    """

    def __init__(
        self,
        *,
        env: Optional[Mapping[str, str]] = None,
        bundle_loader: Callable[[Path], Any] = read_rcv,
        runtime_factory: Callable[[str, str], Any] = get_runtime,
        tokenizer_factory: Callable[[str], Any] = get_tokenizer,
        classifier_factory: Callable[..., Any] = PromptClassifier,
        validator: Callable[..., Mapping[str, Any]] = validate_against_runtime,
    ) -> None:
        self._env = os.environ if env is None else env
        self._bundle_loader = bundle_loader
        self._runtime_factory = runtime_factory
        self._tokenizer_factory = tokenizer_factory
        self._classifier_factory = classifier_factory
        self._validator = validator
        self._lock = threading.RLock()  # published state; held briefly
        self._build_lock = threading.RLock()  # loads and reconciliation; held throughout
        self._clfs: Dict[VersionKey, Any] = {}
        self._runtime_keys: Dict[VersionKey, RuntimeKey] = {}
        self._runtimes: Dict[RuntimeKey, Any] = {}
        self._info: Dict[VersionKey, EffectiveClassifier] = {}
        self._bindings: Dict[
            VersionKey, Tuple[Optional[VersionKey], str, Optional[str]]
        ] = {}
        self._warned: set[Tuple[VersionKey, str]] = set()
        self._loading: set[VersionKey] = set()
        # (consecutive failures, monotonic time of the next allowed attempt):
        # a version that cannot load would otherwise be re-attempted -- and
        # its backbone recompiled -- on every request.
        self._load_failures: Dict[VersionKey, Tuple[int, float]] = {}
        self._loader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="classifier-load")
        # (path, mtime_ns, size) -> bundle: .rcv files are immutable, so a
        # listing re-parses a file only when it is replaced.
        self._listing_cache: Dict[Tuple[str, int, int], Any] = {}

    @staticmethod
    def _normalize_model(model: str) -> str:
        if model not in KNOWN_BACKBONES:
            raise ClassifierNotFoundError(
                f"Unknown model {model!r}; expected one of {sorted(KNOWN_BACKBONES)}"
            )
        return model

    @staticmethod
    def _normalize_version(version: str) -> str:
        if version == "default" or _VERSION_RE.fullmatch(version):
            return version
        raise ClassifierRegistryError(
            f"Invalid classifier version {version!r}; expected 'default' or vN"
        )

    def _source(self, model: str, version: str) -> _VersionSource:
        model = self._normalize_model(model)
        version = self._normalize_version(version)
        packaged_default = default_version_path(model)
        if version == "default":
            if not packaged_default.is_file():
                raise ClassifierRegistryError(
                    f"Packaged default version is missing for {model}: {packaged_default}"
                )
            return _VersionSource(DEFAULT_VERSION, packaged_default, "package")

        packaged = packaged_default.parent / f"{version}.rcv"
        artifact = artifacts_dir(self._env) / model / f"{version}.rcv"
        if packaged.is_file() and artifact.is_file():
            raise ClassifierRegistryError(
                f"Version collision for {model}/{version}: both {packaged} and {artifact} exist"
            )
        if artifact.is_file():
            return _VersionSource(version, artifact, "artifacts")
        if packaged.is_file():
            return _VersionSource(version, packaged, "package")
        raise ClassifierNotFoundError(f"Classifier version not found: {model}/{version}")

    def _runtime(
        self, model: str, patch: Optional[VocabTokenPatch] = None
    ) -> Tuple[RuntimeKey, Any]:
        """The runtime for ``model`` with ``patch`` applied (``None``: unpatched).

        A soft version needs the runtime patched with exactly its rows. Hard
        versions don't use the soft rows and a patch only touches free rows,
        so they reuse any runtime already compiled for the backbone -- a
        patched one first -- instead of forcing a second compilation.
        """
        device = self._env.get("IR_DEVICE", "GPU")
        key: RuntimeKey = (model, device, patch.digest if patch is not None else None)
        with self._lock:
            runtime = self._runtimes.get(key)
            if runtime is None and patch is None:
                same_backbone = [
                    (candidate_key, candidate)
                    for candidate_key, candidate in self._runtimes.items()
                    if candidate_key[:2] == (model, device)
                ]
                same_backbone.sort(key=lambda item: item[0][2] is None)  # patched first
                if same_backbone:
                    return same_backbone[0]
        if runtime is None:  # compiled outside the state lock
            try:
                ir_dir = resolve_ov_model_path(model, self._env)
            except ConfigurationError as exc:  # no IR for this backbone: not loadable
                raise ClassifierRegistryError(str(exc)) from exc
            if patch is None:
                runtime = self._runtime_factory(ir_dir, device)
            else:
                runtime = self._runtime_factory(ir_dir, device, token_patch=patch)
        return key, runtime

    def _ir_dir(self, model: str) -> str:
        try:
            return resolve_ov_model_path(model, self._env)
        except ConfigurationError as exc:  # no IR for this backbone: not loadable
            raise ClassifierRegistryError(str(exc)) from exc

    def _tokenizer(self, model: str) -> Any:
        """The backbone's tokenizer, without compiling the backbone if it is not loaded."""
        device = self._env.get("IR_DEVICE", "GPU")
        with self._lock:
            for (m, d, _digest), runtime in self._runtimes.items():
                if m == model and d == device:
                    return runtime.tokenizer
        return self._tokenizer_factory(self._ir_dir(model))

    def runtime(self, model: str) -> Any:
        """The backbone runtime for ``model`` on ``IR_DEVICE``, compiled if needed.

        For work that needs the backbone itself (packing a hard version). Not
        published: it stays alive only while the caller or a loaded version
        holds it.
        """
        return self._runtime(self._normalize_model(model))[1]

    def _read_bundle(self, model: str, source: _VersionSource) -> Any:
        bundle = self._bundle_loader(source.path)
        if bundle.version != source.canonical_version:
            raise ClassifierRegistryError(
                f"{source.path}: metadata version {bundle.version!r} does not match "
                f"{source.canonical_version!r}"
            )
        return bundle

    def check(
        self,
        model: str,
        version: Optional[str] = None,
        *,
        bundle: Any = None,
        load: bool = True,
    ) -> VersionCheck:
        """Check a version the way activation would, without publishing it.

        ``bundle`` checks an in-memory version that is not written yet;
        otherwise ``version`` is resolved as in :meth:`ensure`. With ``load``
        the full L1/L2/L3 + warmup run on the backbone (compiled if needed and
        released afterwards unless a loaded version uses it); without, the file
        format, L1 and L2 (with the IR's tokenizer alone) are checked, without
        compiling the backbone. A version already serving is not checked again.

        Raises:
            ClassifierNotFoundError: Unknown model or missing version.
            ClassifierRegistryError: The version fails a check.
        """
        model = self._normalize_model(model)
        with self._build_lock:
            origin = "new"
            if bundle is None:
                source = self._source(model, version or "default")
                with self._lock:
                    info = self._info.get((model, source.canonical_version))
                if info is not None:
                    return VersionCheck(
                        info.classifier.bundle, source.origin, info.validation, True
                    )
                origin = source.origin
            try:
                if bundle is None:
                    bundle = self._read_bundle(model, source)
                patch = token_patch(bundle)
                if not load:
                    validation = check_model_name(bundle, model)
                    check_tokenizer(bundle, self._tokenizer(model))
                    validation["L2"] = "ok"
                    return VersionCheck(bundle, origin, validation, False)
                # A token-form version can only be checked on a runtime holding
                # its rows: build (and compile) the patched one for the check.
                _, runtime = self._runtime(model, patch)
                validation = dict(self._validator(bundle, runtime, backbone=model, env=self._env))
                extra = {"vocab_patch": patch} if patch is not None else {}
                classifier = self._classifier_factory(bundle, runtime, cache_size=0, **extra)
                started = time.perf_counter()
                probes = bundle.meta.get("fp_probes") or []
                if probes:
                    classifier.classify(probes[0])
                warmup_ms = (time.perf_counter() - started) * 1000
            except ClassifierRegistryError:
                raise
            except Exception as exc:
                raise ClassifierRegistryError(
                    f"Cannot load {model}/{getattr(bundle, 'version', version)}: {exc}"
                ) from exc
        return VersionCheck(bundle, origin, validation, True, warmup_ms)

    def read(self, model: str, version: str) -> Tuple[Any, str]:
        """``(bundle, origin)`` of a version, for display: no backbone, no checks.

        A version already serving is not read again. Raises
        :class:`ClassifierNotFoundError` or :class:`ClassifierRegistryError`
        (unreadable file).
        """
        model = self._normalize_model(model)
        source = self._source(model, version)
        with self._lock:
            info = self._info.get((model, source.canonical_version))
        if info is not None:
            return info.classifier.bundle, source.origin
        try:
            return self._read_bundle(model, source), source.origin
        except ClassifierRegistryError:
            raise
        except Exception as exc:
            raise ClassifierRegistryError(f"Cannot read {model}/{version}: {exc}") from exc

    def versions(self, model: str) -> list[VersionListing]:
        """Every version file of ``model``, packaged and in the artifacts, in version order.

        For display: files are read (format and file-name checks only, no
        backbone), a version already serving is not read again, and a file
        that cannot be used -- unreadable, a metadata version that does not
        match its name, the same version in both places -- is listed with an
        ``error`` instead of failing the listing.

        Raises:
            ClassifierNotFoundError: Unknown model.
        """
        model = self._normalize_model(model)
        found: Dict[str, list] = {}
        sources = (
            ("package", default_version_path(model).parent),
            ("artifacts", artifacts_dir(self._env) / model),
        )
        for origin, directory in sources:
            if not directory.is_dir():
                continue
            for path in directory.iterdir():
                match = _VERSION_FILE_RE.fullmatch(path.name)
                if match and path.is_file():
                    found.setdefault(match.group(1), []).append((origin, path))

        with self._lock:
            published = dict(self._info)
        listings = []
        for version in sorted(found, key=lambda v: int(v[1:])):
            places = found[version]
            loaded = (model, version) in published
            if len(places) > 1:
                paths = " and ".join(str(path) for _, path in places)
                listings.append(
                    VersionListing(
                        version, places[0][0], None, loaded,
                        f"Version collision for {model}/{version}: both {paths} exist",
                    )
                )
                continue
            origin, path = places[0]
            if loaded:
                bundle = published[(model, version)].classifier.bundle
                listings.append(VersionListing(version, origin, bundle, True))
                continue
            try:
                bundle = self._listed_bundle(model, _VersionSource(version, path, origin))
            except Exception as exc:  # noqa: BLE001 - one bad file must not fail the list
                listings.append(VersionListing(version, origin, None, False, str(exc)))
                continue
            listings.append(VersionListing(version, origin, bundle, False))
        return listings

    def _listed_bundle(self, model: str, source: _VersionSource) -> Any:
        stat = source.path.stat()
        key = (str(source.path), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            bundle = self._listing_cache.get(key)
        if bundle is None:
            bundle = self._read_bundle(model, source)  # raises on a name / metadata mismatch
            with self._lock:
                self._listing_cache = {
                    k: v for k, v in self._listing_cache.items() if k[0] != key[0]
                }  # drop a replaced file's stale entry
                self._listing_cache[key] = bundle
        return bundle

    def published(self) -> set[VersionKey]:
        """The versions currently loaded and serving."""
        with self._lock:
            return set(self._clfs)

    def _ensure(self, model: str, version: str) -> EffectiveClassifier:
        """Load, check and publish one version. Caller holds ``_build_lock``."""
        source = self._source(model, version)
        key = (model, source.canonical_version)
        with self._lock:
            if key in self._clfs:
                return self._info[key]

        try:
            bundle = self._bundle_loader(source.path)
            if bundle.version != source.canonical_version:
                raise ClassifierRegistryError(
                    f"{source.path}: metadata version {bundle.version!r} does not match "
                    f"{source.canonical_version!r}"
                )
            patch = token_patch(bundle)
            if patch is not None:
                # L1 before writing rows: a version that cannot belong to this
                # backbone must fail as such, not inside the graph patch (its
                # ids may not even fit this backbone's tables).
                check_model_name(bundle, model)
            runtime_key, runtime = self._runtime(model, patch)
            validation = dict(
                self._validator(
                    bundle, runtime, backbone=model, env=self._env, l1_checked=patch is not None
                )
            )
            extra = {"vocab_patch": patch} if patch is not None else {}
            classifier = self._classifier_factory(
                bundle,
                runtime,
                cache_size=int(self._env.get("IR_CACHE_SIZE", "256")),
                **extra,
            )
            probes = bundle.meta.get("fp_probes") or []
            if probes:
                classifier.classify(probes[0])
        except ClassifierRegistryError:
            raise
        except Exception as exc:
            raise ClassifierRegistryError(f"Cannot load {model}/{version}: {exc}") from exc

        info = EffectiveClassifier(
            classifier=classifier,
            requested=(model, version),
            effective=key,
            status="ready",
            origin=source.origin,
            validation=validation,
        )
        with self._lock:
            self._runtimes[runtime_key] = runtime
            self._clfs[key] = classifier
            self._runtime_keys[key] = runtime_key
            self._info[key] = info
            self._load_failures.pop(key, None)
            if runtime_key[2] is not None:
                self._move_hard_onto(runtime_key, runtime)
        self._drop_unused_runtimes()
        return info

    def _move_hard_onto(self, runtime_key: RuntimeKey, runtime: Any) -> None:
        """Move hard versions of this backbone onto the newly published patched runtime.

        They run unchanged on it (the patch touches only free rows) -- whatever
        they were on before, an unpatched runtime or a stale patched one -- so
        the runtime they leave is free to be released instead of staying
        compiled next to the new one. Soft token-form versions stay where they
        are: each is bound to its own patch. Caller holds ``_lock``.
        """
        for other_key in list(self._runtime_keys):
            other_runtime_key = self._runtime_keys[other_key]
            if other_runtime_key[:2] != runtime_key[:2]:
                continue
            classifier = self._clfs.get(other_key)
            # a soft token-form version is bound to its own patch: never move it
            # (the flag lives on the classifier; the classifier's bundle knows too)
            if classifier is None or getattr(classifier, "token_form", False):
                continue
            if getattr(getattr(classifier, "bundle", None), "token_form", False):
                continue
            rebind = getattr(classifier, "rebind_runtime", None)
            if rebind is None:
                continue
            rebind(runtime)
            self._runtime_keys[other_key] = runtime_key

    def ensure(self, model: str, version: str) -> EffectiveClassifier:
        """Load and validate exactly one version, without fallback."""
        with self._build_lock:
            return self._ensure(model, version)

    def _bind(self, requested: VersionKey, result: EffectiveClassifier) -> EffectiveClassifier:
        with self._lock:
            self._bindings[requested] = (result.effective, result.status, result.reason)
        return result

    def effective(
        self, model: str, version: str
    ) -> EffectiveClassifier:
        """Resolve requested version, then packaged default, then no classifier."""
        requested = (model, version)
        with self._build_lock:
            try:
                ready = self._ensure(model, version)
                result = EffectiveClassifier(
                    classifier=ready.classifier,
                    requested=requested,
                    effective=ready.effective,
                    status="ready",
                    origin=ready.origin,
                    validation=ready.validation,
                )
                return self._bind(requested, result)
            except Exception as requested_error:
                try:
                    fallback = self._ensure(model, "default")
                except Exception as default_error:
                    reason = f"{requested_error}; default unavailable: {default_error}"
                    self._warn_once(requested, reason)
                    result = EffectiveClassifier(
                        None, requested, None, "unavailable", reason
                    )
                    return self._bind(requested, result)

                reason = str(requested_error)
                self._warn_once(requested, reason)
                result = EffectiveClassifier(
                    classifier=fallback.classifier,
                    requested=requested,
                    effective=fallback.effective,
                    status="degraded",
                    reason=reason,
                    origin=fallback.origin,
                    validation=fallback.validation,
                )
                return self._bind(requested, result)

    def _warn_once(self, key: VersionKey, reason: str) -> None:
        warning = (key, reason)
        if warning not in self._warned:
            self._warned.add(warning)
            logger.warning(
                "Classifier %s/%s is degraded: %s",
                key[0],
                key[1],
                reason,
            )

    def reconcile(
        self, requirements: Iterable[VersionKey]
    ) -> ReconcileResult:
        """Atomically prepare all active requirements, then release stale cache entries."""
        started = time.perf_counter()
        requirements = tuple(dict.fromkeys(requirements))
        with self._build_lock:
            with self._lock:
                old_clfs = dict(self._clfs)
                old_keys = set(old_clfs)
                old_bindings = dict(self._bindings)
            bindings: Dict[VersionKey, EffectiveClassifier] = {}
            desired: set[VersionKey] = set()
            desired_requests = set(requirements)
            unloaded_first = (
                swap_mode(self._env) == "unload_first"
                and any(self.loaded(*requirement) is None for requirement in requirements)
            )
            if unloaded_first:
                for key in tuple(old_keys):
                    self._drop_classifier(key)
                self._drop_unused_runtimes()
            try:
                models = {model for model, _ in requirements}
                for requirement in requirements:
                    binding = self.effective(*requirement)
                    bindings[requirement] = binding
                    if binding.effective is not None:
                        desired.add(binding.effective)
                for model in models:
                    desired_requests.add((model, "default"))
                    served = [
                        binding
                        for (bound_model, _), binding in bindings.items()
                        if bound_model == model and binding.effective is not None
                    ]
                    token_form_serves = any(
                        getattr(
                            getattr(binding.classifier, "bundle", None), "token_form", False
                        )
                        for binding in served
                    )
                    default_is_served = any(
                        binding.effective == (model, DEFAULT_VERSION) for binding in served
                    )
                    if not served or default_is_served or not token_form_serves:
                        default = self.effective(model, "default")
                        if default.effective is not None:
                            desired.add(default.effective)
            except Exception:
                with self._lock:
                    current = set(self._clfs)
                rollback_keys = current if unloaded_first else current - old_keys
                for key in rollback_keys:
                    self._drop_classifier(key)
                if unloaded_first:
                    self._restore(old_keys)
                with self._lock:
                    self._bindings = old_bindings
                self._drop_unused_runtimes()
                raise

            released = len(old_keys) if unloaded_first else 0
            with self._lock:
                stale = set(self._clfs) - desired
            for key in stale:
                self._drop_classifier(key)
                if key in old_keys and not unloaded_first:
                    released += 1
            with self._lock:
                for key in set(self._bindings) - desired_requests:
                    self._bindings.pop(key, None)
                loaded = sum(
                    key not in old_clfs or classifier is not old_clfs[key]
                    for key, classifier in self._clfs.items()
                )
            self._drop_unused_runtimes()
            return ReconcileResult(
                bindings=bindings,
                loaded=loaded,
                released=released,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )

    def _restore(self, keys: Iterable[VersionKey]) -> None:
        for model, version in keys:
            requested = "default" if version == DEFAULT_VERSION else version
            try:
                self._ensure(model, requested)
            except Exception as exc:
                logger.error(
                    "Failed to restore classifier %s/%s after switch failure: %s",
                    model,
                    version,
                    exc,
                )

    def _drop_classifier(self, key: VersionKey) -> None:
        with self._lock:
            self._clfs.pop(key, None)
            self._runtime_keys.pop(key, None)
            self._info.pop(key, None)

    def _drop_unused_runtimes(self) -> None:
        with self._lock:
            used = set(self._runtime_keys.values())
            for key in set(self._runtimes) - used:
                self._runtimes.pop(key, None)

    def release_versions(self, keys: Iterable[VersionKey]) -> None:
        """Drop loaded versions without compiling anything (unload_first swap).

        The running engine's rules must have released their own references
        first; afterwards nothing holds the runtimes and they are freed.
        """
        keys = tuple(keys)
        with self._build_lock:
            with self._lock:
                for key in keys:
                    self._drop_classifier(key)
                for key in tuple(self._bindings):
                    if key in keys:
                        self._bindings.pop(key, None)
            self._drop_unused_runtimes()

    def trigger(self, model: str, version: str) -> None:
        """Queue one best-effort background load for a request-time cache miss.

        Failed attempts back off exponentially (1 s doubling to a 60 s cap):
        a version that cannot load is not re-attempted -- and its backbone not
        recompiled -- on every request. A successful load (here or through
        activation) clears the record.
        """
        key = (model, version)
        with self._lock:
            if key in self._loading:
                return
            failure = self._load_failures.get(key)
            if failure is not None and time.monotonic() < failure[1]:
                return
            self._loading.add(key)

        def load() -> None:
            reason = None
            try:
                result = self.effective(model, version)
                # Success = serving something ready. A request for "default"
                # takes effect as "v1", so the effective key need not equal the
                # requested one; "degraded" means the requested version failed
                # and the fallback is serving -- that one counts as a failure.
                if result.status == "ready" and result.effective is not None:
                    with self._lock:
                        self._load_failures.pop(key, None)
                        self._loading.discard(key)
                    return
                reason = (
                    f"serving {result.effective[1] if result.effective else None} "
                    f"({result.status})"
                )
            except Exception as exc:
                reason = str(exc)
            with self._lock:
                # A version that fails but falls back to the default counts
                # too: its own compile ran and would rerun on every request.
                count = self._load_failures.get(key, (0, 0.0))[0] + 1
                delay = min(60.0, 2.0 ** (count - 1))
                self._load_failures[key] = (count, time.monotonic() + delay)
                self._loading.discard(key)
            logger.warning(
                "Background classifier load failed for %s/%s (retry in %.0fs): %s",
                model,
                version,
                delay,
                reason,
            )

        self._loader.submit(load)

    def loaded(self, model: str, version: str) -> Optional[EffectiveClassifier]:
        """Return a completed requested/fallback binding without loading.

        Safe on request threads: takes only the state lock, never waits for a load.
        """
        with self._lock:
            requested = (model, version)
            binding = self._bindings.get(requested)
            if binding is None:
                return None
            effective, status, reason = binding
            if effective is None:
                return EffectiveClassifier(None, requested, None, status, reason)
            classifier = self._clfs.get(effective)
            info = self._info.get(effective)
            if classifier is None or info is None:
                return None
            return EffectiveClassifier(
                classifier,
                requested,
                effective,
                status,
                reason,
                info.origin,
                info.validation,
            )

    def status(self, model: str, version: str) -> Optional[EffectiveClassifier]:
        """Return the most recent completed status without loading."""
        return self.loaded(model, version)


_REGISTRY: Optional[ClassifierRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_registry() -> ClassifierRegistry:
    """Process-wide classifier registry."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = ClassifierRegistry()
        return _REGISTRY


def set_registry_for_testing(registry: Optional[ClassifierRegistry]) -> None:
    """Replace the process registry; intended for isolated unit tests."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        _REGISTRY = registry
