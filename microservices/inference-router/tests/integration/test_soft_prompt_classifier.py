# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The shipped soft versions run on a real backbone.

Per backbone, each layer runs when its inputs are configured:

* contract -- the backbone IR (``IR_OV_MODEL`` / ``IR_OV_MODEL_QWEN35_2B``,
  ``IR_OV_MODEL_QWEN3_0P6B``): results are well-formed;
* HF parity -- plus the HuggingFace weights (``HF_MODEL_QWEN35_2B`` /
  ``HF_MODEL_QWEN3_0P6B``): per query, the router's input
  ``[soft][pad x 64][query]`` gives the same zone probabilities as the
  HuggingFace reference computed the way the soft prompts were trained and
  evaluated -- in a batch, where Qwen3.5's linear-attention layers zero the
  pad block (|diff| <= 1e-2, same decision).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from src.exceptions import ConfigurationError
from src.rsd.model_based import settings
from src.rsd.model_based.base import decide
from src.rsd.model_based.format import read_rcv

pytestmark = pytest.mark.slow

QUERIES = [
    "What is 2 + 2?",
    "用一句话解释什么是光合作用。",
    "Design a distributed consensus protocol tolerant to Byzantine faults and prove its safety.",
    "请比较 Raft 和 Paxos 在成员变更、日志压缩和读一致性上的差异，并给出工程实现上的取舍。",
    "Write a haiku about spring.",
    "帮我 fix 这个 Python bug：list index out of range",
]


def _classifier(backbone: str):
    try:
        ir_dir = settings.resolve_ov_model_path(backbone)
    except ConfigurationError:
        pytest.skip(f"no IR configured for {backbone} ({settings.ov_model_env_var(backbone)})")
    from src.rsd.model_based.classifier import PromptClassifier
    from src.rsd.model_based.runtime import get_runtime
    from src.rsd.model_based.vocab_tokens import token_patch

    bundle = read_rcv(settings.default_version_path(backbone))
    config = json.loads((Path(ir_dir) / "config.json").read_text())
    if config.get("text_config", config).get("hidden_size") != bundle.hidden:
        pytest.skip(f"{ir_dir} is not a {backbone} IR")
    # Soft versions are token form: they run on a runtime patched with their rows.
    patch = token_patch(bundle)
    runtime = get_runtime(ir_dir, os.environ.get("IR_DEVICE", "CPU"), token_patch=patch)
    return PromptClassifier(bundle, runtime, cache_size=0, vocab_patch=patch)


def _hf_env(backbone: str) -> str:
    return "HF_MODEL_" + backbone.upper().replace("-", "_").replace(".", "P")


@pytest.mark.parametrize("backbone", sorted(settings.KNOWN_BACKBONES))
def test_shipped_soft_version_is_well_formed(backbone):
    clf = _classifier(backbone)
    for query in QUERIES:
        result = clf.classify(query)
        assert list(result.scores) == ["local", "cloud"]
        assert sum(result.scores.values()) == pytest.approx(1.0, abs=1e-6)
        assert result.index == decide(list(result.scores.values()), result.threshold)
        assert (result.kind, result.version) == ("soft", "v1")
        assert len(result.raw["class_probs"]) == 12


@pytest.mark.parametrize("backbone", sorted(settings.KNOWN_BACKBONES))
def test_matches_the_huggingface_reference(backbone):
    clf = _classifier(backbone)
    hf_model = os.environ.get(_hf_env(backbone))
    if not hf_model:
        pytest.skip(f"set {_hf_env(backbone)} to the HuggingFace weights to compare")
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")

    tokenizer = transformers.AutoTokenizer.from_pretrained(hf_model)
    model = transformers.AutoModelForCausalLM.from_pretrained(hf_model, dtype=torch.float32)
    decoder = model.float().eval().model
    bundle = clf.bundle
    padding = bundle.meta["render"]["padding"]
    soft = torch.from_numpy(bundle.prompt.copy())[None]
    for query in QUERIES:
        ids = tokenizer(query).input_ids
        assert clf._runtime.encode(query).tolist() == ids  # same tokenizer
        n_pad = padding["between_soft_and_query"]
        with torch.no_grad():  # no position_ids, as trained
            tokens = decoder.embed_tokens(torch.tensor([[padding["pad_token_id"]] * n_pad + ids]))
            mask = torch.tensor([[1] * soft.shape[1] + [0] * n_pad + [1] * len(ids)])
            # A batch of two copies: HF zeroes masked positions in the linear-attention
            # layers only for batches > 1 -- the training-time computation.
            out = decoder(
                inputs_embeds=torch.cat([soft, tokens], 1).expand(2, -1, -1),
                attention_mask=mask.expand(2, -1),
                use_cache=False,
            )
        hidden = out.last_hidden_state[0, -1].double().numpy()
        logits = bundle.head_weight.astype(np.float64) @ hidden + bundle.head_bias
        probs = np.exp(logits - logits.max())
        p_local_hf = (probs / probs.sum())[np.asarray(bundle.class_zones) == 0].sum()

        result = clf.classify(query)
        assert result.scores["local"] == pytest.approx(p_local_hf, abs=1e-2), query
        assert result.index == (0 if p_local_hf >= 0.5 else 1), query
