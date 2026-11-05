# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""A hard version packed from text runs like the same prompt given as a file.

On a real backbone (``IR_OV_MODEL`` / ``IR_OV_MODEL_<BACKBONE>``): the version
packed from ``text`` passes the registry's L1/L2/L3 + warmup after a round trip
through the ``.rcv`` file, and classifies every query exactly like the
multi-class ``prompt_file`` classifier built from the same text and labels.
"""

from __future__ import annotations

import os

import pytest

from src.exceptions import ConfigurationError
from src.rsd.model_based import settings

pytestmark = pytest.mark.slow

LABELS = ["local", "cloud", "planning"]
QUERIES = [
    "Polish this paragraph for clarity.",
    "Break our monolith-to-microservices migration into phases with milestones "
    "and dependencies.",
    "用一句话解释什么是光合作用。",
    "Find the race condition in this Go worker pool and fix it.",
]


def _prompt() -> str:
    text = (settings._DEFAULT_PROMPT_DIR / "multiclass.example.txt").read_text(encoding="utf-8")
    return text.split("NOTE:")[0]


@pytest.mark.parametrize("backbone", sorted(settings.KNOWN_BACKBONES))
def test_packed_hard_version_matches_the_prompt_file_classifier(backbone, tmp_path):
    try:
        ir_dir = settings.resolve_ov_model_path(backbone)
    except ConfigurationError:
        pytest.skip(f"no IR configured for {backbone} ({settings.ov_model_env_var(backbone)})")
    from src.rsd.model_based.format import write_rcv
    from src.rsd.model_based.hard_version import build_hard_bundle
    from src.rsd.model_based.registry import ClassifierRegistry
    from src.rsd.model_based.runtime import get_runtime

    device = os.environ.get("IR_DEVICE", "CPU")
    runtime = get_runtime(ir_dir, device)
    bundle = build_hard_bundle(
        runtime, model=backbone, version="v2", text=_prompt(), labels=LABELS, threshold=0.7
    )
    (tmp_path / backbone).mkdir()
    write_rcv(tmp_path / backbone / "v2.rcv", bundle)
    env = {
        settings.ov_model_env_var(backbone): ir_dir,
        "IR_ARTIFACTS_DIR": str(tmp_path),
        "IR_DEVICE": device,
        "IR_CACHE_SIZE": "0",
    }
    info = ClassifierRegistry(env=env).ensure(backbone, "v2")  # read back, L1/L2/L3, warmup
    assert info.validation["L3_min_cos"] > 0.999
    assert info.validation["hard_head_min_cos"] > 0.999

    cfg = settings.multiclass_classifier_config(ir_dir, LABELS, _prompt(), 0.7)
    cfg.device, cfg.cache_size = device, 0
    reference = settings.build_classifier(cfg)
    assert reference._runtime is runtime  # same backbone, compiled once
    for query in QUERIES:
        packed, direct = info.classifier.classify(query), reference.classify(query)
        assert packed.index == direct.index, query
        for label in LABELS:
            assert packed.scores[label] == pytest.approx(direct.scores[label], abs=1e-4), query
