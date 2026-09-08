# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Tests for ASRComponent diarization startup policy (ITEP-95359).

Confirms that:
- models.asr.diarization=true never silently disables diarization on any error.
- Authentication/access errors produce a clear startup failure.
- Non-auth diarization init errors also produce a clear startup failure.
- GPU device string 'gpu' raises instead of silently disabling (ITEP-95359 root cause).
- models.asr.diarization=false does not require HF credentials or the diarizer.
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy ML libraries before any app import.
# ---------------------------------------------------------------------------
for _mod in [
    "torch", "torch.serialization", "torch.torch_version",
    "pyannote", "pyannote.audio", "pyannote.audio.core", "pyannote.audio.core.task",
    "openvino", "openvino_genai",
    "librosa", "soundfile", "sounddevice",
    "whisper", "whispercpp",
]:
    sys.modules.setdefault(_mod, MagicMock())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_backend_cls():
    class _Backend:
        def __init__(self, *_a, **_kw):
            pass
    return _Backend


def _cfg(*, diarization: bool = True, diarization_device: str = "CPU"):
    return SimpleNamespace(
        app=SimpleNamespace(use_ov_genai=False),
        models=SimpleNamespace(
            asr=SimpleNamespace(
                provider="openai",
                name="whisper-base",
                device="CPU",
                diarization=diarization,
                hf_token="hf_tok" if diarization else None,
                temperature=0.0,
                models_base_path="models",
                weight_format=None,
            ),
            diarization=SimpleNamespace(
                provider="huggingface",
                name="pyannote/speaker-diarization-community-1",
                device=diarization_device,
                models_base_path="models",
                min_speakers=1,
                max_speakers=2,
                identity=SimpleNamespace(
                    enabled=False,
                    similarity_threshold=0.75,
                    lock_min_duration_sec=0.75,
                    session_ttl_seconds=1800.0,
                ),
            ),
        ),
        pipeline=SimpleNamespace(delete_chunks_after_use=False),
        sentiment=SimpleNamespace(enabled=False),
    )


def _reset(asr_mod):
    asr_mod.ASRComponent._model = None
    asr_mod.ASRComponent._config = None
    asr_mod.ASRComponent._pyannote_diarizer = None
    asr_mod.ASRComponent._pyannote_diarizer_key = None
    asr_mod.ASRComponent._speaker_identity_store = None


def _make_asr(asr_mod):
    return asr_mod.ASRComponent(
        session_id="test",
        provider="openai",
        model_name="whisper-base",
        device="CPU",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.tier1
def test_diarization_disabled_does_not_call_diarizer():
    """When diarization=false the diarizer is never instantiated."""
    import components.asr_component as asr_mod
    import components.asr.diarization.pyannote_diarizer as pd_mod

    with (
        patch.object(asr_mod, "config", _cfg(diarization=False)),
        patch.object(asr_mod, "ENABLE_DIARIZATION", False),
        patch.object(asr_mod.ASRComponent, "_resolve_backend",
                     staticmethod(lambda p, m, d: (_fake_backend_cls(), ("k",), d))),
        patch.object(pd_mod, "PyannoteDiarizer") as mock_diar,
    ):
        _reset(asr_mod)
        comp = _make_asr(asr_mod)

    mock_diar.assert_not_called()
    assert comp.pyannote_diarizer is None
    assert not comp.enable_diarization


@pytest.mark.tier1
def test_diarization_auth_error_raises_not_warns():
    """A 403/auth error from PyannoteDiarizer must abort startup (not silently disable)."""
    import components.asr_component as asr_mod
    import components.asr.diarization.pyannote_diarizer as pd_mod

    with (
        patch.object(asr_mod, "config", _cfg(diarization=True, diarization_device="CPU")),
        patch.object(asr_mod, "ENABLE_DIARIZATION", True),
        patch.object(asr_mod.ASRComponent, "_resolve_backend",
                     staticmethod(lambda p, m, d: (_fake_backend_cls(), ("k",), d))),
        patch("utils.ensure_model._resolve_hf_token", return_value="hf_tok"),
        patch("utils.openvino_runtime_validation.resolve_diarization_torch_device", return_value="cpu"),
        patch.object(pd_mod, "PyannoteDiarizer",
                     side_effect=RuntimeError("403 Forbidden")),
    ):
        _reset(asr_mod)
        with pytest.raises(RuntimeError, match="HF token/access error"):
            _make_asr(asr_mod)


@pytest.mark.tier1
def test_diarization_non_auth_error_raises_not_silently_disables():
    """Any non-auth error from PyannoteDiarizer must also abort startup.

    ITEP-95359 regression: previously torch.device('gpu') raised
    'Expected one of cpu, cuda ... at start of device string: gpu'
    which was caught, logged as WARNING, and diarization was silently disabled.
    """
    import components.asr_component as asr_mod
    import components.asr.diarization.pyannote_diarizer as pd_mod

    with (
        patch.object(asr_mod, "config", _cfg(diarization=True, diarization_device="CPU")),
        patch.object(asr_mod, "ENABLE_DIARIZATION", True),
        patch.object(asr_mod.ASRComponent, "_resolve_backend",
                     staticmethod(lambda p, m, d: (_fake_backend_cls(), ("k",), d))),
        patch("utils.ensure_model._resolve_hf_token", return_value="hf_tok"),
        patch("utils.openvino_runtime_validation.resolve_diarization_torch_device", return_value="cpu"),
        patch.object(pd_mod, "PyannoteDiarizer",
                     side_effect=RuntimeError("some unexpected internal error")),
    ):
        _reset(asr_mod)
        with pytest.raises(RuntimeError, match="Startup aborted"):
            _make_asr(asr_mod)


@pytest.mark.tier1
def test_diarization_device_gpu_without_backend_raises_not_silently_disables():
    """Regression: diarization.device=GPU failures must abort startup.

    GPU/NPU diarization now uses the OV-backed path, so this test must simulate
    failure in OVBackedPyannoteDiarizer initialization and assert startup aborts
    rather than silently disabling diarization.
    """
    # ITEP-95359 root-cause fix: GPU/NPU validation now happens via OpenVINO device
    # enumeration in validate_diarization_device_configuration() (called at
    # startup before ASRComponent.__init__), not inside __init__ via torch.device().
    # That path is tested in test_openvino_runtime_validation.py.
    #
    # Regression here: any error propagated INTO __init__ must abort startup, not
    # silently disable.  Simulate an OV probe failure reaching the except block.
    import components.asr_component as asr_mod
    import components.asr.diarization.ov_pyannote_diarizer as ov_pd_mod

    with (
        patch.object(asr_mod, "config", _cfg(diarization=True, diarization_device="GPU")),
        patch.object(asr_mod, "ENABLE_DIARIZATION", True),
        patch.object(asr_mod.ASRComponent, "_resolve_backend",
                     staticmethod(lambda p, m, d: (_fake_backend_cls(), ("k",), d))),
        patch("utils.ensure_model._resolve_hf_token", return_value="hf_tok"),
        # resolve_diarization_torch_device now just returns the device string;
        # actual OV availability is validated before __init__.
        # Simulate OV-backed diarizer failing to initialize.
        patch("utils.openvino_runtime_validation.resolve_diarization_torch_device",
              return_value="GPU"),
        patch.object(ov_pd_mod, "OVBackedPyannoteDiarizer",
                     side_effect=RuntimeError("simulated OV diarizer failure")),
    ):
        _reset(asr_mod)
        with pytest.raises(RuntimeError, match="Startup aborted"):
            _make_asr(asr_mod)
