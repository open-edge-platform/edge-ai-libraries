# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pack a trained soft prompt (flat artifacts) into one ``.rcv`` classifier version.

Input is the training output ``<prefix>.npy`` (soft prompt ``[k, H]``),
``<prefix>.output_embedding.npz`` (12-class head), ``<prefix>.meta.json`` and
``<prefix>.route.json``. The backbone fingerprint (``fp_hidden``) is the
post-norm last-position hidden state of each probe text -- raw text, no chat
template, no soft prefix -- computed with the HuggingFace model in fp32
(``fp_ref = hf-fp32``); the router compares its own backbone against it
before using the version as the L3 compatibility check.

The 12 difficulty classes are merged into two routing zones: local (classes
greater than or equal to ``--local-from``) and cloud. The router takes the more
likely zone unless it is below ``--threshold``. The operating point ``--tau``
(route local when p(local) > tau; default: route.json's threshold) is folded
into the head bias of the local classes, so no separate decision rule is needed.

Versions are named ``vN`` and live in a directory named after the backbone:
``<dir>/<backbone>/vN.rcv``. Example (the version shipped as ``default``)::

    python -m src.rsd.model_based.pack_rcv \\
        --artifact artifacts/router/qwen35-2b/qwen35_2b_head_k8 \\
        --backbone qwen35-2b --hf-model /path/to/Qwen3.5-2B \\
        --version v1 --out src/rsd/model_based/prompts/qwen35-2b/v1.rcv

Every version is written in token form: the slots hold the trained soft
vectors, head and bias -- the data the router writes into the backbone's
vocabulary rows -- and the metadata names the canonical vocabulary ids
(``soft_token_ids`` / ``label_token_ids``, continuing the original vocab; see
``src/rsd/model_based/vocab_tokens.py``).

Needs ``torch`` + ``transformers`` for the fingerprint (imported only when
packing); the router itself does not, and never imports this module.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.rsd.model_based.bundle import KIND_SOFT, ClassifierBundle
from src.rsd.model_based.format import write_rcv
from src.rsd.model_based.settings import FP_PROBES, KNOWN_BACKBONES
from src.rsd.model_based.vocab_tokens import add_token_ids

FP_REF = "hf-fp32"

# The 12-class soft head: class c is the round()ed sum of 11 candidate models'
# accuracies on the sample (0 = all fail -> cloud, 11 = all succeed -> local).
# Classes >= LOCAL_FROM merge into zone 0 (local), the rest into zone 1 (cloud).
LOCAL_FROM = 6
ZONE_NAMES = ["local", "cloud"]

# Input layout the soft prompts were trained with: raw query, soft prefix first,
# 64 masked pad positions between soft prefix and query, and queries truncated
# from the left. The pad token id (the tokenizer's pad token, or eos when it has
# none, as in training) is filled in per backbone.
RENDER = {
    "template": "raw",
    "wrap": "",
    "soft_position": "before",
    "truncation": "left",
    "padding": {"between_soft_and_query": 64},
}

# fingerprint(probes) -> (fp_hidden [n_probes, H], token ids of probes[0])
Fingerprint = Callable[[Sequence[str]], Tuple[np.ndarray, List[int]]]


def _class_semantics(num_classes: int) -> List[str]:
    """Total-score range of each class: class c holds round(total_score) == c."""
    top = num_classes - 1
    return [
        f"[{max(c - 0.5, 0):g}, {min(c + 0.5, top):g}{']' if c == top else ')'}"
        for c in range(num_classes)
    ]


_VERSION = re.compile(r"v[1-9][0-9]*")


def check_destination(out: str, backbone: str, version: str) -> None:
    """``out`` must be ``<backbone>/<version>.rcv`` and ``version`` must be ``vN``."""
    if not _VERSION.fullmatch(version):
        raise ValueError(f"version must be vN (v1, v2, ...), got {version!r}")
    path = Path(out)
    if path.suffix != ".rcv" or path.stem != version or path.parent.name != backbone:
        raise ValueError(f"output must be <dir>/{backbone}/{version}.rcv, got {out}")


def fold_tau(bias: np.ndarray, class_zones: Sequence[int], tau: float) -> np.ndarray:
    """Shift the local classes' bias so "more likely zone" equals "p(local) > tau".

    Adding ``log((1 - tau) / tau)`` to every zone-0 logit scales p(local) by
    ``w = (1 - tau) / tau`` before renormalising, and ``w * p > 1 - p`` iff
    ``p > tau``.
    """
    if not 0.0 < tau < 1.0:
        raise ValueError(f"tau must be within (0, 1), got {tau}")
    shift = np.float32(np.log((1.0 - tau) / tau))
    local = np.asarray(class_zones) == 0
    return np.where(local, bias + shift, bias).astype(np.float32)


def build_bundle(
    artifact: str,
    backbone: str,
    version: str,
    fingerprint: Fingerprint,
    local_from: int = LOCAL_FROM,
    tau: Optional[float] = None,
    threshold: float = 0.5,
    note: str = "",
    probes: Sequence[str] = FP_PROBES,
    *,
    pad_token_id: int,
) -> ClassifierBundle:
    """Assemble the soft ``.rcv`` bundle for the flat artifact ``artifact`` (path prefix)."""
    if backbone not in KNOWN_BACKBONES:
        raise ValueError(
            f"unknown backbone {backbone!r}; expected one of {sorted(KNOWN_BACKBONES)}"
        )
    if not _VERSION.fullmatch(version):
        raise ValueError(f"version must be vN (v1, v2, ...), got {version!r}")
    if local_from != LOCAL_FROM and tau is None:
        raise ValueError(
            "local_from and tau are chosen together: pass --tau when changing --local-from"
        )
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be within [0, 1], got {threshold}")

    soft = np.load(f"{artifact}.npy").astype(np.float32)
    head = np.load(f"{artifact}.output_embedding.npz")
    train_meta: Dict = json.loads(Path(f"{artifact}.meta.json").read_text(encoding="utf-8"))
    route_path = Path(f"{artifact}.route.json")
    route: Dict = json.loads(route_path.read_text(encoding="utf-8")) if route_path.exists() else {}

    hidden = int(soft.shape[1])
    weight = head["weight"].astype(np.float32)
    num_classes = int(weight.shape[0])
    class_labels = (
        [int(c) for c in head["labels"]] if "labels" in head.files else list(range(num_classes))
    )
    class_zones = [0 if c >= local_from else 1 for c in class_labels]
    if len(set(class_zones)) != 2:
        raise ValueError(f"local_from={local_from} must leave at least one class in each zone")
    tau = float(route.get("threshold", 0.5) if tau is None else tau)
    bias = fold_tau(head["bias"].astype(np.float32), class_zones, tau)
    fp_hidden, fp_token_ids = fingerprint(probes)

    meta = {
        "model_name": KNOWN_BACKBONES[backbone],
        "version": version,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hidden": hidden,
        "fp_probes": list(probes),
        "fp_ref": FP_REF,
        "fp_token_ids": [int(t) for t in fp_token_ids],
        "num_classes": num_classes,
        "class_labels": class_labels,
        "class_semantics": _class_semantics(num_classes),
        "class_zones": class_zones,
        "zone_names": list(ZONE_NAMES),
        "threshold": float(threshold),
        "tau_folded": tau,
        "text_max_tokens": int(train_meta.get("text_max_tokens", 2040)),
        "truncation_side": str(train_meta.get("truncation_side", "left")),
        "render": dict(
            RENDER,
            soft_position=train_meta.get("soft_position", "before"),
            padding=dict(RENDER["padding"], pad_token_id=int(pad_token_id)),
        ),
        "train_meta": train_meta,
        "route_metrics": route,
    }
    if note:
        meta["note"] = note
    # Token form: name the vocabulary rows the soft vectors and head rows go to.
    return add_token_ids(
        ClassifierBundle(
            kind=KIND_SOFT,
            prompt=soft,
            head_weight=weight,
            head_bias=bias,
            fp_hidden=np.asarray(fp_hidden, dtype=np.float32),
            meta=meta,
        )
    )


def hf_pad_token_id(hf_model: str) -> int:
    """The id training padded with.

    Preference order: the tokenizer's pad token, the generation config's pad
    token (Llama-3.2 sets 128004 there while leaving the tokenizer's pad
    unset -- guessing eos breaks the trained pad block), then the eos token.
    """
    from transformers import AutoTokenizer, GenerationConfig

    tokenizer = AutoTokenizer.from_pretrained(hf_model)
    if tokenizer.pad_token_id is not None:
        return int(tokenizer.pad_token_id)
    try:
        pad = GenerationConfig.from_pretrained(hf_model).pad_token_id
        if pad is not None:
            return int(pad)
    except (OSError, ValueError):
        pass
    return int(tokenizer.eos_token_id)


def hf_fingerprint(hf_model: str) -> Fingerprint:
    """Fingerprint with the HuggingFace model in fp32 on CPU (post-norm last hidden)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(hf_model)
    model = AutoModelForCausalLM.from_pretrained(hf_model, dtype=torch.float32).eval()

    def fingerprint(probes: Sequence[str]) -> Tuple[np.ndarray, List[int]]:
        rows, first_ids = [], None
        for probe in probes:
            ids = tokenizer(probe, return_tensors="pt").input_ids
            first_ids = ids[0].tolist() if first_ids is None else first_ids
            with torch.no_grad():
                out = model(input_ids=ids, output_hidden_states=True)
            rows.append(out.hidden_states[-1][0, -1].float().numpy())  # after the final norm
        return np.stack(rows), first_ids

    return fingerprint


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--artifact", required=True, help="flat artifact path prefix (without .npy)"
    )
    parser.add_argument("--backbone", required=True, choices=sorted(KNOWN_BACKBONES))
    parser.add_argument(
        "--hf-model", required=True, help="HuggingFace model dir/id for the fingerprint"
    )
    parser.add_argument("--version", required=True, help="vN; the file name must match")
    parser.add_argument(
        "--out", required=True, help="<dir>/<backbone>/<version>.rcv (must not exist)"
    )
    parser.add_argument("--local-from", type=int, default=LOCAL_FROM)
    parser.add_argument(
        "--tau",
        type=float,
        default=None,
        help="operating point, folded into the head bias " "(default: route.json threshold)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="abstain below this zone probability " "(0.5 with two zones: never abstain)",
    )
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    check_destination(args.out, args.backbone, args.version)

    bundle = build_bundle(
        args.artifact,
        args.backbone,
        args.version,
        hf_fingerprint(args.hf_model),
        local_from=args.local_from,
        tau=args.tau,
        threshold=args.threshold,
        note=args.note,
        pad_token_id=hf_pad_token_id(args.hf_model),
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out = write_rcv(args.out, bundle)
    print(
        f"wrote {out} ({out.stat().st_size} bytes): {bundle.model_name} {bundle.version} "
        f"(k={bundle.prompt.shape[0]}, classes={bundle.num_classes}, "
        f"zones={bundle.zone_names}, threshold={bundle.threshold}, "
        f"tau folded={bundle.meta.get('tau_folded')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
