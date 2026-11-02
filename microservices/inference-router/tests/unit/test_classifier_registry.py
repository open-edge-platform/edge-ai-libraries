# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ClassifierRegistry lifecycle, fallback and concurrency tests without OpenVINO."""
from __future__ import annotations
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
import pytest
from src.exceptions import ConfigurationError
from src.rsd.engine.decision import DecisionEngine
from src.rsd.engine.strategy import ProviderSelector
from src.rsd.model_based.registry import ClassifierRegistry, ClassifierRegistryError, EffectiveClassifier, ReconcileResult
from src.rsd.model_based.rule import ModelBasedRule
MODEL = 'qwen35-2b'

class FakeRuntime:
    pass

class FakeClassifier:

    def __init__(self, bundle, runtime, cache_size=0):
        self.bundle = bundle
        self.runtime = runtime
        self.cache_size = cache_size
        self.seen = []

    def classify(self, text):
        self.seen.append(text)
        return SimpleNamespace(index=0)

    def rebind_runtime(self, runtime):
        if getattr(self.bundle, 'token_form', False):
            raise ValueError('a soft version is bound to its patched runtime')
        self.runtime = runtime

def _bundle(version):
    return SimpleNamespace(version=version, model_name='Qwen/Qwen3.5-2B', meta={'fp_probes': ['warmup']})

@pytest.fixture
def registry_parts(tmp_path):
    model_dir = tmp_path / 'ir'
    model_dir.mkdir()
    artifacts = tmp_path / 'artifacts'
    env = {'IR_OV_MODEL': str(model_dir), 'IR_ARTIFACTS_DIR': str(artifacts), 'IR_DEVICE': 'CPU', 'IR_CACHE_SIZE': '7'}
    runtime_calls = []
    classifier_calls = []
    validation_calls = []

    def runtime_factory(path, device):
        runtime_calls.append((path, device))
        return FakeRuntime()

    def classifier_factory(bundle, runtime, cache_size):
        classifier_calls.append(bundle.version)
        return FakeClassifier(bundle, runtime, cache_size)

    def validator(bundle, runtime, **kwargs):
        validation_calls.append((bundle.version, runtime, kwargs))
        return {'L1': 'ok', 'L2': 'ok', 'L3_min_cos': 1.0}
    registry = ClassifierRegistry(env=env, bundle_loader=lambda path: _bundle(path.stem), runtime_factory=runtime_factory, classifier_factory=classifier_factory, validator=validator)
    return SimpleNamespace(registry=registry, env=env, artifacts=artifacts, runtime_calls=runtime_calls, classifier_calls=classifier_calls, validation_calls=validation_calls)

def _artifact(parts, version):
    path = parts.artifacts / MODEL / f'{version}.rcv'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'test')
    return path

@pytest.mark.unit
def test_versions_share_one_runtime_and_publish_only_after_warmup(registry_parts):
    _artifact(registry_parts, 'v2')
    _artifact(registry_parts, 'v3')
    first = registry_parts.registry.ensure(MODEL, 'v2')
    second = registry_parts.registry.ensure(MODEL, 'v3')
    assert first.classifier.runtime is second.classifier.runtime
    assert registry_parts.runtime_calls == [(registry_parts.env['IR_OV_MODEL'], 'CPU')]
    assert registry_parts.classifier_calls == ['v2', 'v3']
    assert first.classifier.seen == ['warmup']
    assert first.validation['L3_min_cos'] == 1.0

@pytest.mark.unit
def test_request_threads_do_not_wait_for_a_background_load(registry_parts):
    registry = registry_parts.registry
    building, release = (threading.Event(), threading.Event())

    def slow_runtime(path, device):
        building.set()
        release.wait(timeout=10)
        return FakeRuntime()
    registry._runtime_factory = slow_runtime
    registry.trigger(MODEL, 'default')
    assert building.wait(timeout=5)
    answered = []
    reader = threading.Thread(target=lambda: answered.append(registry.loaded(MODEL, 'default')))
    reader.start()
    reader.join(timeout=2)
    assert not reader.is_alive() and answered == [None]
    release.set()
    for _ in range(100):
        if registry.loaded(MODEL, 'default') is not None:
            break
        threading.Event().wait(0.05)
    assert registry.loaded(MODEL, 'default').status == 'ready'

def test_concurrent_ensure_builds_version_once(registry_parts):
    _artifact(registry_parts, 'v2')
    barrier = threading.Barrier(8)
    results = []

    def load():
        barrier.wait()
        results.append(registry_parts.registry.ensure(MODEL, 'v2').classifier)
    threads = [threading.Thread(target=load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len({id(classifier) for classifier in results}) == 1
    assert registry_parts.classifier_calls == ['v2']
    assert len(registry_parts.runtime_calls) == 1

@pytest.mark.unit
def test_missing_requested_version_falls_back_to_packaged_default(registry_parts):
    result = registry_parts.registry.effective(MODEL, 'v99')
    assert result.status == 'degraded'
    assert result.requested == (MODEL, 'v99')
    assert result.effective == (MODEL, 'v1')
    assert result.origin == 'package'
    assert result.classifier.bundle.version == 'v1'

@pytest.mark.unit
def test_artifact_cannot_shadow_packaged_version(registry_parts):
    _artifact(registry_parts, 'v1')
    with pytest.raises(ClassifierRegistryError, match='collision'):
        registry_parts.registry.ensure(MODEL, 'v1')
    assert registry_parts.registry.ensure(MODEL, 'default').origin == 'package'

@pytest.mark.unit
def test_metadata_version_must_match_filename(registry_parts):
    _artifact(registry_parts, 'v2')
    registry_parts.registry._bundle_loader = lambda path: _bundle('v7')
    with pytest.raises(ClassifierRegistryError, match='metadata version'):
        registry_parts.registry.ensure(MODEL, 'v2')
    assert not registry_parts.registry._clfs

@pytest.mark.unit
def test_reconcile_keeps_default_and_releases_stale_version(registry_parts):
    _artifact(registry_parts, 'v2')
    _artifact(registry_parts, 'v3')
    first = registry_parts.registry.reconcile([(MODEL, 'v2')])
    second = registry_parts.registry.reconcile([(MODEL, 'v3')])
    assert first.loaded == 2
    assert second.loaded == 1 and second.released == 1
    assert set(registry_parts.registry._clfs) == {(MODEL, 'v1'), (MODEL, 'v3')}
    assert len(registry_parts.runtime_calls) == 1

@pytest.mark.unit
def test_reconcile_with_a_failing_version_keeps_the_previous_state(registry_parts):
    _artifact(registry_parts, 'v2')
    _artifact(registry_parts, 'v3')
    registry_parts.registry.reconcile([(MODEL, 'v2')])
    before = dict(registry_parts.registry._clfs)

    def reject_v3(bundle, runtime, **kwargs):
        if bundle.version == 'v3':
            raise ValueError('bad fingerprint')
        return {'L1': 'ok', 'L2': 'ok', 'L3_min_cos': 1.0}
    registry_parts.registry._validator = reject_v3
    result = registry_parts.registry.reconcile([(MODEL, 'v3')])
    assert result.bindings[MODEL, 'v3'].effective == (MODEL, 'v1')
    assert set(registry_parts.registry._clfs) == {(MODEL, 'v1')}

@pytest.mark.unit
def test_unload_first_degraded_version_falls_back_to_the_default(registry_parts):
    _artifact(registry_parts, 'v2')
    _artifact(registry_parts, 'v3')
    registry_parts.registry.reconcile([(MODEL, 'v2')])
    registry_parts.env['IR_SWAP_MODE'] = 'unload_first'

    def reject_v3(bundle, runtime, **kwargs):
        if bundle.version == 'v3':
            raise ValueError('bad fingerprint')
        return {'L1': 'ok', 'L2': 'ok', 'L3_min_cos': 1.0}
    registry_parts.registry._validator = reject_v3
    result = registry_parts.registry.reconcile([(MODEL, 'v3')])
    binding = result.bindings[MODEL, 'v3']
    assert binding.effective == (MODEL, 'v1')
    assert set(registry_parts.registry._clfs) == {(MODEL, 'v1')}
    assert len(registry_parts.runtime_calls) == 3

@pytest.mark.unit
def test_unload_first_reports_reloaded_default_and_new_version(registry_parts):
    _artifact(registry_parts, 'v2')
    _artifact(registry_parts, 'v3')
    registry_parts.registry.reconcile([(MODEL, 'v2')])
    registry_parts.env['IR_SWAP_MODE'] = 'unload_first'
    result = registry_parts.registry.reconcile([(MODEL, 'v3')])
    assert result.loaded == 2
    assert result.released == 2
    assert set(registry_parts.registry._clfs) == {(MODEL, 'v1'), (MODEL, 'v3')}

@pytest.mark.unit
def test_invalid_swap_mode_is_rejected(registry_parts):
    _artifact(registry_parts, 'v2')
    registry_parts.env['IR_SWAP_MODE'] = 'sideways'
    with pytest.raises(ConfigurationError, match='IR_SWAP_MODE'):
        registry_parts.registry.reconcile([(MODEL, 'v2')])

@pytest.mark.unit
def _engine_with_selector(rule, **selector):
    engine = DecisionEngine.__new__(DecisionEngine)
    engine.strategy_names = ['Versioned']
    fields = {'label': None, 'cost': None, 'complexity': None, **selector}
    engine.strategy_definitions = {'Versioned': SimpleNamespace(rules=[SimpleNamespace(rule=rule)], provider_selector=SimpleNamespace(label=fields['label'], cost=fields['cost'], capability=SimpleNamespace(complexity=fields['complexity'])))}
    return engine

@pytest.mark.unit
@pytest.mark.parametrize('selector', [{'label': {0: 'local', 1: 'cloud', 2: 'planning'}}, {'complexity': {0: 0.3, 1: 0.8, 2: 0.6}}, {'label': 'cloud'}, {'cost': 0, 'complexity': 0.5}])
def test_matching_or_fixed_selectors_are_silent(selector, caplog):
    rule = object()
    classifier = SimpleNamespace(bundle=SimpleNamespace(zone_names=['local', 'cloud', 'planning']))
    with caplog.at_level('WARNING'):
        _engine_with_selector(rule, **selector)._check_classifier_zones(rule, classifier)
    assert not caplog.records

@pytest.mark.unit
def test_zone_mismatches_warn_but_never_reject(caplog):
    rule = object()
    classifier = SimpleNamespace(bundle=SimpleNamespace(zone_names=['local', 'cloud']))
    engine = _engine_with_selector(rule, label={0: 'local'}, complexity={0: 0.3, 1: 0.8, 2: 0.9})
    with caplog.at_level('WARNING'):
        engine._check_classifier_zones(rule, classifier)
    messages = [record.getMessage() for record in caplog.records]
    assert any(('provider_selector.label has no entry for zone(s) [1] (cloud)' in m for m in messages))
    assert any(('provider_selector.capability.complexity maps zone(s) [2]' in m for m in messages))

@pytest.mark.unit
def test_decision_engine_reconciles_and_binds_versioned_rule():
    requirement = (MODEL, 'v2')
    rule = SimpleNamespace(registry_requirement=requirement, classifier=None)
    rule.bind_classifier = lambda classifier: setattr(rule, 'classifier', classifier)
    classifier = SimpleNamespace(bundle=SimpleNamespace(zone_names=['local', 'cloud']))
    binding = EffectiveClassifier(classifier, requirement, requirement, 'ready')
    registry = Mock()
    registry.reconcile.return_value = ReconcileResult({requirement: binding}, loaded=1, released=0, elapsed_ms=1.0)
    engine = DecisionEngine.__new__(DecisionEngine)
    engine.strategy_names = ['Versioned']
    engine.strategy_definitions = {'Versioned': SimpleNamespace(rules=[SimpleNamespace(rule=rule)], provider_selector=ProviderSelector(label={0: 'local', 1: 'cloud'}))}
    with patch('src.rsd.engine.decision.get_registry', return_value=registry):
        result = engine.reconcile_classifiers()
    registry.reconcile.assert_called_once_with([requirement])
    assert result.loaded == 1
    assert rule.classifier is classifier

class BackgroundRegistry:

    def __init__(self):
        self.binding = None
        self.triggers = 0

    def loaded(self, model, version):
        return self.binding

    def trigger(self, model, version):
        self.triggers += 1

@pytest.mark.unit
def test_versioned_rule_never_loads_synchronously_on_request():
    registry = BackgroundRegistry()
    rule = ModelBasedRule(model=MODEL, version='v2', registry=registry)
    assert rule.evaluate(_request()) == -1
    assert registry.triggers == 1
    classifier = FakeClassifier(_bundle('v2'), FakeRuntime())
    registry.binding = EffectiveClassifier(classifier, (MODEL, 'v2'), (MODEL, 'v2'), 'ready')
    assert rule.evaluate(_request()) == 0
    assert classifier.seen == ['query']

def _request():
    from src.models import ChatCompletionMessage, ChatCompletionRequest, ChatCompletionRole
    return ChatCompletionRequest(model='auto', messages=[ChatCompletionMessage(role=ChatCompletionRole.USER, content='query')])

@pytest.mark.unit
@pytest.mark.parametrize('params,match', [({'model': 'unknown', 'version': 'v1'}, 'model'), ({'version': 1}, 'version'), ({'version': 'latest'}, 'default.*vN'), ({'version': 'v2', 'labels': ['a', 'b'], 'prompt_file': 'p'}, 'mutually exclusive'), ({'version': 'v2', 'threshold': 0.7}, 'mutually exclusive')])
def test_versioned_rule_rejects_invalid_parameters(params, match):
    with pytest.raises(ConfigurationError, match=match):
        ModelBasedRule(**params)

class PatchedRuntime:

    def __init__(self, token_patch=None):
        self.token_patch_digest = token_patch.digest if token_patch is not None else None

def _hard_bundle(version, rng_seed=0):
    from src.rsd.model_based.bundle import KIND_HARD, ClassifierBundle
    rng = np.random.default_rng(rng_seed)
    meta = {'model_name': 'Qwen/Qwen3.5-2B', 'version': version, 'created': '2026-10-26T00:00:00Z', 'hidden': 4, 'fp_probes': ['warmup'], 'fp_ref': 'openvino', 'fp_token_ids': [1], 'num_classes': 2, 'class_semantics': ['local', 'cloud'], 'label_tokens': ['A', 'B'], 'label_token_ids': [32, 33], 'threshold': 0.7, 'text_max_tokens': 0, 'truncation_side': 'left', 'render': {'template': 'qwen_chat'}, 'content_hash': 'sha256:test'}
    return ClassifierBundle(kind=KIND_HARD, prompt='Pick one.', head_weight=rng.standard_normal((2, 4)).astype(np.float32), head_bias=np.zeros(2, np.float32), fp_hidden=rng.standard_normal((1, 4)).astype(np.float32), meta=meta)

def _real_bundle(version, rng_seed=0):
    from src.rsd.model_based.bundle import KIND_SOFT, ClassifierBundle
    rng = np.random.default_rng(rng_seed)
    meta = {'model_name': 'Qwen/Qwen3.5-2B', 'version': version, 'created': '2026-10-26T00:00:00Z', 'hidden': 4, 'fp_probes': ['warmup'], 'fp_ref': 'hf-fp32', 'fp_token_ids': [1], 'num_classes': 4, 'class_labels': [0, 1, 2, 3], 'class_semantics': ['a', 'b', 'c', 'd'], 'class_zones': [1, 1, 0, 0], 'zone_names': ['local', 'cloud'], 'threshold': 0.5, 'text_max_tokens': 64, 'truncation_side': 'left', 'render': {'template': 'raw', 'soft_position': 'before', 'padding': {}}, 'soft_token_ids': list(range(248077, 248080)), 'label_token_ids': list(range(248080, 248084))}
    return ClassifierBundle(kind=KIND_SOFT, prompt=rng.standard_normal((3, 4)).astype(np.float32), head_weight=rng.standard_normal((4, 4)).astype(np.float32), head_bias=np.zeros(4, np.float32), fp_hidden=rng.standard_normal((1, 4)).astype(np.float32), meta=meta)

def _token_registry(tmp_path):
    """A registry over real .rcv files with a recording runtime factory."""
    from src.rsd.model_based.format import write_rcv
    from src.rsd.model_based.registry import ClassifierRegistry
    model_dir = tmp_path / 'ir'
    model_dir.mkdir(exist_ok=True)
    artifacts = tmp_path / 'artifacts' / MODEL
    artifacts.mkdir(parents=True)
    write_rcv(artifacts / 'v2.rcv', _real_bundle('v2', rng_seed=1))
    write_rcv(artifacts / 'v3.rcv', _real_bundle('v3', rng_seed=2))
    write_rcv(artifacts / 'v4.rcv', _hard_bundle('v4', rng_seed=3))
    calls = []

    def runtime_factory(path, device, token_patch=None):
        calls.append(token_patch.digest if token_patch is not None else None)
        return PatchedRuntime(token_patch)
    registry = ClassifierRegistry(env={'IR_OV_MODEL': str(model_dir), 'IR_ARTIFACTS_DIR': str(tmp_path / 'artifacts'), 'IR_DEVICE': 'CPU'}, runtime_factory=runtime_factory, classifier_factory=lambda *args, **kw: FakeClassifier(args[0], args[1], cache_size=kw.get('cache_size', 0)), validator=lambda bundle, runtime, **kwargs: {'L1': 'ok', 'L2': 'ok', 'L3_min_cos': 1.0})
    return (registry, calls)

@pytest.mark.unit
def test_token_runtimes_are_shared_and_hard_versions_follow_the_newest(tmp_path):
    registry, calls = _token_registry(tmp_path)
    hard = registry.ensure(MODEL, 'v4').classifier
    unpatched = hard.runtime
    first = registry.ensure(MODEL, 'v2')
    repeated = registry.ensure(MODEL, 'v2')
    assert first.classifier.runtime is repeated.classifier.runtime is hard.runtime
    assert hard.runtime is not unpatched and len(calls) == 2
    assert set(registry._runtimes) == {(MODEL, 'CPU', hard.runtime.token_patch_digest)}
    registry.ensure(MODEL, 'v3')
    assert hard.runtime is not unpatched and hard.runtime.token_patch_digest != calls[1]
    with registry._lock:
        registry._drop_classifier((MODEL, 'v2'))
    registry._drop_unused_runtimes()
    digests = {key[2] for key in registry._runtimes}
    assert digests == {calls[2]}

@pytest.mark.unit
def test_reconcile_default_preload_matches_what_serves(tmp_path):
    """The packaged default is preloaded only when it shares a runtime with
    what serves (hard-only policy) or is the fallback of a broken version;
    next to a serving token-form version it would be a second compiled
    backbone, so it stays unloaded."""
    registry, calls = _token_registry(tmp_path)
    registry.reconcile([(MODEL, 'v2')])
    assert (MODEL, 'v1') not in registry._clfs and len(calls) == 1
    registry.reconcile([(MODEL, 'v4')])
    assert (MODEL, 'v1') in registry._clfs
    hard = registry._clfs[MODEL, 'v4'].runtime
    default = registry._clfs[MODEL, 'v1'].runtime
    assert hard is default and len(registry._runtimes) == 1
    registry.reconcile([(MODEL, 'v9')])
    binding = registry.loaded(MODEL, 'v9')
    assert binding.effective == (MODEL, 'v1') and len(calls) == 2

@pytest.mark.unit
def test_token_form_error_paths_and_background_backoff(tmp_path):
    import threading
    registry, calls = _token_registry(tmp_path)
    from src.rsd.model_based.format import write_rcv
    other = _real_bundle('v5', rng_seed=4)
    assert other.model_name == 'Qwen/Qwen3.5-2B'
    wrong_dir = tmp_path / 'artifacts' / 'qwen3-0.6b'
    wrong_dir.mkdir(parents=True)
    write_rcv(wrong_dir / 'v5.rcv', other)
    with pytest.raises(ClassifierRegistryError, match='model_name'):
        registry.ensure('qwen3-0.6b', 'v5')
    assert calls == []
    from src.rsd.model_based.runtime import TokenFormError

    def failing_factory(path, device, token_patch=None):
        if token_patch is not None:
            raise TokenFormError('weight-compressed; token-form versions need FP16/BF16 IRs')
        return PatchedRuntime(None)
    registry._runtime_factory = failing_factory
    with pytest.raises(ClassifierRegistryError, match='FP16/BF16'):
        registry.ensure(MODEL, 'v2')
    result = registry.effective(MODEL, 'v2')
    assert result.classifier is None and result.status == 'unavailable'
    attempted = threading.Event()
    attempts = []

    def counting_validator(bundle, runtime, **kwargs):
        if bundle.version == 'v2':
            attempts.append(bundle.version)
            attempted.set()
        raise ValueError('bad fingerprint')
    registry._runtime_factory = lambda path, device, token_patch=None: PatchedRuntime(token_patch)
    registry._validator = counting_validator
    registry.trigger(MODEL, 'v2')
    assert attempted.wait(timeout=10)
    while (MODEL, 'v2') in registry._loading:
        __import__('time').sleep(0.01)
    assert registry._load_failures[MODEL, 'v2'][0] == 1
    compiles_after_first = len(calls)
    registry.trigger(MODEL, 'v2')
    assert len(calls) == compiles_after_first
    with registry._lock:
        count, _ = registry._load_failures[MODEL, 'v2']
        registry._load_failures[MODEL, 'v2'] = (count, 0.0)
    attempted.clear()
    registry.trigger(MODEL, 'v2')
    assert attempted.wait(timeout=10)
    assert len(attempts) == 2
    registry._validator = lambda bundle, runtime, **kwargs: {'L1': 'ok', 'L2': 'ok'}
    registry.trigger(MODEL, 'default')
    while (MODEL, 'default') in registry._loading:
        __import__('time').sleep(0.01)
    assert registry._load_failures.get((MODEL, 'default')) is None

@pytest.mark.unit
def test_version_listing_reads_each_file_once_until_it_is_replaced(tmp_path):
    import os

    artifacts = tmp_path / "artifacts"
    (artifacts / MODEL).mkdir(parents=True)
    target = artifacts / MODEL / "v2.rcv"
    target.write_bytes(b"first")
    reads = []

    def loader(path):
        reads.append(path.name)
        return _bundle(path.stem)

    registry = ClassifierRegistry(
        env={"IR_OV_MODEL": str(tmp_path), "IR_ARTIFACTS_DIR": str(artifacts)},
        bundle_loader=loader,
    )
    first = [v.version for v in registry.versions(MODEL)]
    registry.versions(MODEL)
    assert "v2" in first and reads.count("v2.rcv") == 1  # cached: immutable files

    target.write_bytes(b"replaced!")
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    registry.versions(MODEL)
    assert reads.count("v2.rcv") == 2  # a replaced file is read again
    assert len([k for k in registry._listing_cache if k[0] == str(target)]) == 1


@pytest.mark.unit
def test_version_listing_rejects_unknown_models(tmp_path):
    from src.rsd.model_based.registry import ClassifierNotFoundError

    with pytest.raises(ClassifierNotFoundError):
        ClassifierRegistry(env={}).versions("qwen9-100b")
