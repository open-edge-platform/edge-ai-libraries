# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The shipped default versions match the deployed backbone.

L2: the IR's tokenizer reproduces the packed token ids of probe 0.
L3: the IR's post-norm hidden of every probe has cosine >= 0.98 with the HF
fp32 fingerprint packed in the file.

Runs per backbone when its IR is configured (``IR_OV_MODEL`` /
``IR_OV_MODEL_QWEN35_2B`` for qwen35-2b, ``IR_OV_MODEL_QWEN3_0P6B`` for
qwen3-0.6b). Measured 2026-10-20: FP16 and INT8 IRs pass (min cos >= 0.993),
INT4 IRs do not (0.958 for 2B, 0.932 for 0.6B) -- the check is meant to refuse them.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.exceptions import ConfigurationError
from src.rsd.model_based import settings
from src.rsd.model_based.format import read_rcv

FP_MIN_COS = 0.98

pytestmark = pytest.mark.slow


def _ir_dir(backbone: str) -> str:
    try:
        return settings.resolve_ov_model_path(backbone)
    except ConfigurationError:
        pytest.skip(f"no IR configured for {backbone} ({settings.ov_model_env_var(backbone)})")


@pytest.mark.parametrize("backbone", sorted(settings.KNOWN_BACKBONES))
def test_default_version_matches_the_backbone(backbone):
    ir_dir = _ir_dir(backbone)
    from src.rsd.model_based.runtime import get_runtime

    bundle = read_rcv(settings.default_version_path(backbone))
    runtime = get_runtime(ir_dir, "CPU")
    if runtime.hidden_size != bundle.hidden:
        pytest.skip(f"{ir_dir} is not a {backbone} IR (hidden {runtime.hidden_size})")

    probes = bundle.meta["fp_probes"]
    assert runtime.encode(probes[0]).tolist() == bundle.meta["fp_token_ids"]  # L2
    for probe, reference in zip(probes, bundle.fp_hidden):  # L3
        hidden = runtime.last_hidden(runtime.embed(runtime.encode(probe))).astype(np.float64)
        reference = reference.astype(np.float64)
        cos = hidden @ reference / np.linalg.norm(hidden) / np.linalg.norm(reference)
        assert cos >= FP_MIN_COS, f"{probe!r}: cos {cos:.5f}"
