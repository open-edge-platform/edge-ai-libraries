# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The soft versions shipped in ``src/rsd/model_based/prompts/<backbone>/v1.rcv`` — no OpenVINO.

Every known backbone ships one version with the code, ``v1``, which a strategy
refers to as ``default``. It is packed from the trained flat artifacts by
``tools/pack_rcv.py``. These tests pin what the files must say; the backbone
fingerprint itself is checked against a real IR in
``tests/integration/test_default_rcv_fingerprint.py``.
"""

import pytest

from src.rsd.model_based import settings
from src.rsd.model_based.bundle import KIND_SOFT
from src.rsd.model_based.format import read_rcv

HIDDEN = {"qwen35-2b": 2048, "qwen3-0.6b": 1024, "llama3-1b": 2048}

# Soft prompt length the training sweep produced per backbone.
K = {"qwen35-2b": 8, "qwen3-0.6b": 8, "llama3-1b": 3}

# Query budget the version was trained with (text_max_tokens in the .meta.json).
TEXT_MAX_TOKENS = {"qwen35-2b": 2040, "qwen3-0.6b": 2040, "llama3-1b": 2045}


@pytest.mark.unit
def test_every_known_backbone_ships_the_expected_default_version():
    assert set(HIDDEN) == set(settings.KNOWN_BACKBONES)
    for backbone in settings.KNOWN_BACKBONES:
        path = settings.default_version_path(backbone)
        assert path.is_file()
        assert (path.parent.name, path.name) == (backbone, f"{settings.DEFAULT_VERSION}.rcv")


@pytest.mark.unit
@pytest.mark.parametrize("backbone", sorted(HIDDEN))
def test_default_version_contents(backbone):
    bundle = read_rcv(settings.default_version_path(backbone))
    hidden = HIDDEN[backbone]

    assert (
        (bundle.kind, bundle.version) == (KIND_SOFT, settings.DEFAULT_VERSION) == (KIND_SOFT, "v1")
    )
    assert bundle.model_name == settings.KNOWN_BACKBONES[backbone]
    assert bundle.hidden == hidden
    assert bundle.prompt.shape == (K[backbone], hidden)
    assert bundle.head_weight.shape == (12, hidden) and bundle.head_bias.shape == (12,)
    assert bundle.class_labels == list(range(12))
    # 12 ordered difficulty classes merged into two zones: 6-11 local (zone 0), 0-5 cloud.
    assert bundle.class_zones == [1] * 6 + [0] * 6 and bundle.zone_names == ["local", "cloud"]
    # threshold 0.5 with two zones never abstains (route.json's 80.5% / 74.8% are measured so);
    # route.json's tau 0.5 folds into a zero bias shift.
    assert (bundle.threshold, bundle.meta["tau_folded"]) == (0.5, 0.5)
    render = bundle.meta["render"]
    # The pad block's token id is the tokenizer's pad token: the 2B's linear attention sees it.
    pad_id = {"qwen35-2b": 248044, "qwen3-0.6b": 151643, "llama3-1b": 128004}[backbone]
    assert render["template"] == "raw" and render["soft_position"] == "before"
    assert render["padding"] == {"between_soft_and_query": 64, "pad_token_id": pad_id}
    assert (bundle.meta["text_max_tokens"], bundle.meta["truncation_side"]) == (
        TEXT_MAX_TOKENS[backbone],
        "left",
    )
    # Fingerprint: HF fp32 post-norm hidden of each probe, plus probe 0's token ids.
    assert bundle.meta["fp_ref"] == "hf-fp32"
    assert bundle.fp_hidden.shape == (len(bundle.meta["fp_probes"]), hidden)
    assert bundle.meta["fp_token_ids"]


@pytest.mark.unit
def test_unknown_backbone_has_no_default_version():
    from src.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError, match="Unknown backbone"):
        settings.default_version_path("llama")
