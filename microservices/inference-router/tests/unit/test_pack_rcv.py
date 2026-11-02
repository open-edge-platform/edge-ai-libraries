# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""tools/pack_rcv.py: flat soft-prompt artifacts -> one .rcv version (fingerprint stubbed)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from src.rsd.model_based.format import read_rcv, write_rcv

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "pack_rcv.py"
_spec = importlib.util.spec_from_file_location("pack_rcv", _TOOL)
pack_rcv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack_rcv)

HIDDEN = 16


def _flat_artifact(tmp_path, route=None) -> str:
    prefix = tmp_path / "toy_head_k4"
    rng = np.random.default_rng(0)
    np.save(f"{prefix}.npy", rng.normal(size=(4, HIDDEN)).astype(np.float32))
    np.savez(
        f"{prefix}.output_embedding.npz",
        weight=rng.normal(size=(12, HIDDEN)).astype(np.float32),
        bias=rng.normal(size=12).astype(np.float32),
        labels=np.arange(12),
    )
    Path(f"{prefix}.meta.json").write_text(
        json.dumps({"text_max_tokens": 1000, "truncation_side": "left"})
    )
    Path(f"{prefix}.route.json").write_text(
        json.dumps(route or {"threshold": 0.45, "accuracy": 0.8})
    )
    return str(prefix)


def _fingerprint(probes):
    return np.ones((len(probes), HIDDEN), np.float32), [1, 2, 3]


@pytest.mark.unit
def test_pack_round_trips_the_flat_artifact(tmp_path):
    prefix = _flat_artifact(tmp_path)
    bundle = pack_rcv.build_bundle(
        prefix, "qwen3-0.6b", "v3", _fingerprint, pad_token_id=7, note="toy"
    )
    path = write_rcv(tmp_path / "v3.rcv", bundle)
    back = read_rcv(path)

    np.testing.assert_array_equal(back.prompt, np.load(f"{prefix}.npy"))
    np.testing.assert_array_equal(
        back.head_weight, np.load(f"{prefix}.output_embedding.npz")["weight"]
    )
    assert (back.model_name, back.version, back.kind) == ("Qwen/Qwen3-0.6B", "v3", "soft")
    # Token form: k=4 soft tokens, then the 12 class tokens, continuing the vocabulary.
    assert back.token_form
    assert back.soft_token_ids == list(range(151669, 151673))
    assert back.label_token_ids == list(range(151673, 151685))
    # Classes 6-11 merge into zone 0 (local); route.json's tau 0.45 is folded into their bias.
    assert back.class_zones == [1] * 6 + [0] * 6 and back.zone_names == ["local", "cloud"]
    assert back.threshold == 0.5 and back.meta["tau_folded"] == pytest.approx(0.45)
    assert back.meta["render"]["padding"] == {"between_soft_and_query": 64, "pad_token_id": 7}
    bias = np.load(f"{prefix}.output_embedding.npz")["bias"]
    np.testing.assert_allclose(back.head_bias[:6], bias[:6])
    np.testing.assert_allclose(back.head_bias[6:], bias[6:] + np.log(0.55 / 0.45), rtol=1e-6)
    assert back.meta["fp_token_ids"] == [1, 2, 3] and back.fp_hidden.shape == (4, HIDDEN)
    assert back.meta["route_metrics"]["accuracy"] == 0.8 and back.meta["note"] == "toy"
    assert (
        back.meta["class_semantics"][0] == "[0, 0.5)"
        and back.meta["class_semantics"][-1] == "[10.5, 11]"
    )


@pytest.mark.unit
def test_local_from_and_tau_are_chosen_together(tmp_path):
    prefix = _flat_artifact(tmp_path)
    with pytest.raises(ValueError, match="pass --tau"):
        pack_rcv.build_bundle(
            prefix, "qwen3-0.6b", "v3", _fingerprint, pad_token_id=7, local_from=7
        )
    bundle = pack_rcv.build_bundle(
        prefix, "qwen3-0.6b", "v3", _fingerprint, pad_token_id=7, local_from=7, tau=0.4
    )
    assert bundle.class_zones == [1] * 7 + [0] * 5 and bundle.meta["tau_folded"] == pytest.approx(
        0.4
    )
    with pytest.raises(ValueError, match="each zone"):
        pack_rcv.build_bundle(
            prefix, "qwen3-0.6b", "v3", _fingerprint, pad_token_id=7, local_from=12, tau=0.5
        )


@pytest.mark.unit
@pytest.mark.parametrize("tau", [0.3, 0.5, 0.62])
def test_folded_tau_reproduces_p_local_above_tau(tau):
    """More likely zone with the folded bias  ==  p(local) > tau with the original head."""
    from src.rsd.model_based.base import decide, zone_probs

    rng = np.random.default_rng(0)
    zones = [1] * 6 + [0] * 6
    bias = rng.normal(size=12).astype(np.float32)
    folded = pack_rcv.fold_tau(bias, zones, tau)
    logits = rng.normal(0, 2, size=(20_000, 12)).astype(np.float32)

    def softmax(x):
        e = np.exp(x - x.max())
        return e / e.sum()

    mismatches = 0
    for row in logits:
        p_local = softmax(row + bias)[6:].sum()
        if abs(p_local - tau) < 1e-5:
            continue  # float32 rounding at the exact boundary
        expected = 0 if p_local > tau else 1
        mismatches += decide(zone_probs(softmax(row + folded), zones), 0.5) != expected
    assert mismatches == 0


@pytest.mark.unit
def test_unknown_backbone_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown backbone"):
        pack_rcv.build_bundle(_flat_artifact(tmp_path), "llama", "v1", _fingerprint, pad_token_id=7)


@pytest.mark.unit
@pytest.mark.parametrize(
    "out,version,ok",
    [
        ("x/qwen3-0.6b/v3.rcv", "v3", True),
        ("x/qwen3-0.6b/v4.rcv", "v3", False),  # the file name is the version
        ("x/qwen35-2b/v3.rcv", "v3", False),  # the directory is the backbone
        ("x/qwen3-0.6b.rcv", "v3", False),
        ("x/qwen3-0.6b/default.rcv", "default", False),  # "default" is an alias, not a version
        ("x/qwen3-0.6b/v0.rcv", "v0", False),
    ],
)
def test_destination_follows_the_version_layout(out, version, ok):
    if ok:
        pack_rcv.check_destination(out, "qwen3-0.6b", version)
    else:
        with pytest.raises(ValueError):
            pack_rcv.check_destination(out, "qwen3-0.6b", version)


@pytest.mark.unit
def test_version_must_be_vn(tmp_path):
    with pytest.raises(ValueError, match="vN"):
        pack_rcv.build_bundle(
            _flat_artifact(tmp_path), "qwen3-0.6b", "default", _fingerprint, pad_token_id=7
        )


def test_there_is_no_head_form_repack_mode():
    """Every version is packed in token form; the old --vocab-tokens re-pack is gone."""
    with pytest.raises(SystemExit):
        pack_rcv.main(["--vocab-tokens", "--backbone", "qwen35-2b", "--in", "x.rcv",
                       "--version", "v1", "--out", "/tmp/qwen35-2b/v1.rcv"])
