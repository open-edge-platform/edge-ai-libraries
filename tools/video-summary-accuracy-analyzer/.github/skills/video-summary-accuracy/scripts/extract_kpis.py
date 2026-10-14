#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Extract and validate accuracy KPIs from a raw analyzer `/evaluate` response.

Reads the JSON list returned for a Markdown comparison, validates it, and prints
a normalized KPI JSON object on stdout. Uses only the Python standard library.

Usage:
    python3 extract_kpis.py <raw_result.json>

Exit status:
    0  KPIs extracted and validated (warnings may still be listed).
    1  Response is invalid or missing required sections; do not report a verdict.
    2  Usage or file read error.
"""

import json
import math
import sys
from statistics import fmean

RATIO_TOLERANCE = 0.01
SENTENCE_KEYS = ("reference_sentence", "matched_sentence", "similarity_score",
                 "factual_consistency", "bert_score", "rouge_score")
FACTUAL_KEYS = ("total_sentences_compared", "entailment", "neutral", "contradiction",
                "entailment_ratio", "neutral_ratio", "contradiction_ratio",
                "average_cosine_score", "MENLI_Score")
TEMPORAL_KEYS = ("temporal_score", "pairwise_order_accuracy", "temporal_violations",
                 "out_of_order_pairs", "total_pairs", "kendall_tau_norm")


def finite_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    return None


def parse_fraction_numerator(value):
    """Parse values serialized as 'x/y' (e.g. '0.5927/1.0') without evaluating text."""
    if isinstance(value, str) and "/" in value:
        try:
            number = float(value.split("/", 1)[0].strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return finite_number(value)


def mean_or_none(values):
    values = [v for v in values if v is not None]
    return round(fmean(values), 4) if values else None


def extract(data):
    errors, warnings = [], []
    if not isinstance(data, list):
        return None, ["Response is not a JSON list (a .md comparison returns a list)."], warnings

    sentences, temporal, factual_list = [], None, None
    for item in data:
        if not isinstance(item, dict):
            continue
        if "Temporal Coherence Summary" in item:
            temporal = item["Temporal Coherence Summary"]
        elif "Factual Consistency Summary" in item:
            factual_list = item["Factual Consistency Summary"]
        elif "reference_sentence" in item:
            sentences.append(item)

    if not sentences:
        errors.append("No sentence entries found.")
    if not isinstance(factual_list, list):
        errors.append("Missing 'Factual Consistency Summary'.")
        factual_list = []
    if not isinstance(temporal, dict):
        errors.append("Missing 'Temporal Coherence Summary'.")
        temporal = {}

    for i, entry in enumerate(sentences):
        missing = [k for k in SENTENCE_KEYS if k not in entry]
        if missing:
            warnings.append(f"Sentence entry {i} missing keys: {missing}")

    factual_raw = {m.get("Metric"): m.get("Value") for m in factual_list if isinstance(m, dict)}
    factual = {}
    for key in FACTUAL_KEYS:
        if key not in factual_raw:
            factual[key] = None
            warnings.append(f"Factual metric '{key}' unavailable.")
            continue
        parsed = (parse_fraction_numerator(factual_raw[key]) if key == "average_cosine_score"
                  else finite_number(factual_raw[key]))
        if parsed is None:
            warnings.append(f"Factual metric '{key}' is not a finite number: {factual_raw[key]!r}")
        factual[key] = parsed
    for direction in ("Reference → Generated", "Generated → Reference"):
        if direction in factual_raw:
            factual[direction] = finite_number(factual_raw[direction])

    temporal_out = {}
    for key in TEMPORAL_KEYS:
        value = finite_number(temporal.get(key))
        if value is None:
            warnings.append(f"Temporal metric '{key}' unavailable.")
        temporal_out[key] = value

    total = factual.get("total_sentences_compared")
    counts = [factual.get(k) for k in ("entailment", "neutral", "contradiction")]
    ratios = [factual.get(k) for k in ("entailment_ratio", "neutral_ratio", "contradiction_ratio")]
    if total is None:
        errors.append("total_sentences_compared is unavailable.")
    else:
        if total != len(sentences):
            warnings.append(f"total_sentences_compared ({total}) != sentence entries ({len(sentences)}).")
        if all(c is not None for c in counts) and sum(counts) != total:
            errors.append(f"Factual counts sum to {sum(counts)}, expected {total}.")
    if all(r is not None for r in ratios) and abs(sum(ratios) - 1.0) > RATIO_TOLERANCE and total:
        errors.append(f"Factual ratios sum to {sum(ratios):.4f}, expected 1.0.")
    menli = factual.get("MENLI_Score")
    if menli is not None and not -2.0 <= menli <= 1.0:
        warnings.append(f"MENLI_Score {menli} is outside the expected -2..1 range.")

    def sentence_metric(entry, *path):
        node = entry
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return finite_number(node)

    derived = {
        "mean_bert_f1": mean_or_none(sentence_metric(s, "bert_score", "f1_score") for s in sentences),
        "mean_rouge1_f1": mean_or_none(sentence_metric(s, "rouge_score", "rouge1", "f1_score") for s in sentences),
        "mean_rouge2_f1": mean_or_none(sentence_metric(s, "rouge_score", "rouge2", "f1_score") for s in sentences),
        "mean_rougeL_f1": mean_or_none(sentence_metric(s, "rouge_score", "rougeL", "f1_score") for s in sentences),
        "note": "Arithmetic means of per-sentence scores; not document-level scores.",
    }

    pairs = [
        {
            "index": i,
            "reference_sentence": s.get("reference_sentence"),
            "matched_sentence": s.get("matched_sentence"),
            "factual_consistency": s.get("factual_consistency"),
            "similarity_score": finite_number(s.get("similarity_score")),
        }
        for i, s in enumerate(sentences)
    ]
    flagged = [p for p in pairs if p["factual_consistency"] in ("contradiction", "neutral")]
    weakest = sorted((p for p in pairs if p["similarity_score"] is not None),
                     key=lambda p: p["similarity_score"])[:3]

    result = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "sentence_entries": len(sentences),
        "factual": factual,
        "temporal": temporal_out,
        "derived_sentence_means": derived,
        "flagged_pairs": flagged,
        "weakest_semantic_matches": weakest,
    }
    return result, errors, warnings


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [f"Cannot read JSON: {exc}"]}, indent=2))
        return 2

    result, errors, _ = extract(data)
    if result is None:
        result = {"valid": False, "errors": errors}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
