#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Validate the GenAI BGE adapter against real pipeline outputs on local hardware.

Requires a BGE export with openvino_model.xml and openvino_tokenizer.xml.
Runs English/Chinese fixtures, checks original-index mapping and input isolation,
and varies request top_n while keeping the same compiled pipeline.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

FIXTURES = [
    ("en", "What is the capital of France?", [
        "Whales are mammals that live in the ocean.",
        "Tokyo is the capital of Japan.",
        "Paris is the capital of France.",
        "The Eiffel Tower is a famous landmark in Paris.",
    ]),
    ("zh", "中国的首都是哪里？", [
        "鲸鱼是生活在海洋中的哺乳动物。",
        "东京是日本的首都。",
        "北京是中国的首都。",
        "上海是中国的重要经济中心。",
    ]),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--device", default="CPU")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import openvino as ov
    import openvino_genai
    from llama_index.core.schema import NodeWithScore, TextNode
    from core.postprocessor import RerankProcessor
    from inference.ov_adapter import OpenVINOGenAIReranking

    started = time.perf_counter()
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": str(args.model.resolve()),
        "device": args.device,
        "device_name": ov.Core().get_property(args.device, "FULL_DEVICE_NAME"),
        "openvino": ov.__version__,
        "openvino_genai": openvino_genai.__version__,
        "fixtures": [],
    }
    print(f"Loading {args.model} on {args.device} ({report['device_name']})", flush=True)
    adapter = OpenVINOGenAIReranking(
        str(args.model.resolve()), device=args.device, top_n=1, keep_retrieval_score=True,
    )
    processor = RerankProcessor(adapter, top_n=1)
    native = adapter._ov_pipe
    report["load_seconds"] = time.perf_counter() - started
    print(f"Loaded in {report['load_seconds']:.2f}s", flush=True)

    for language, query, texts in FIXTURES:
        nodes = [NodeWithScore(node=TextNode(id_=str(i), text=text), score=0.99 - i / 100)
                 for i, text in enumerate(texts)]
        before = [node.model_dump() for node in nodes]
        raw = native.rerank(query, texts)
        assert len(raw) == len(nodes), f"Pipeline truncated candidates: {raw}"
        assert sorted(index for index, _ in raw) == list(range(len(nodes)))
        assert all(math.isfinite(score) for _, score in raw)
        assert [score for _, score in raw] == sorted((score for _, score in raw), reverse=True)
        assert raw[0][0] == 2, f"Expected the explicit answer first: {raw}"
        assert [index for index, _ in raw] != list(range(len(nodes))), "Fixture must exercise reordered results"

        checks = []
        for top_n in (1, 3, 2, 6, 1):
            tick = time.perf_counter()
            ranked = processor.run(nodes, query_str=query, top_n=top_n)
            elapsed = time.perf_counter() - tick
            expected = raw[:top_n]
            assert [node.node.node_id for node in ranked] == [str(index) for index, _ in expected]
            for node, (index, score) in zip(ranked, expected):
                assert math.isclose(node.score, score, rel_tol=1e-6, abs_tol=1e-6)
                assert node.node.metadata["retrieval_score"] == before[index]["score"]
                assert node is not nodes[index] and node.node is not nodes[index].node
            assert [node.model_dump() for node in nodes] == before, "Recall data was mutated"
            assert adapter._ov_pipe is native, "Pipeline was replaced"
            checks.append({"top_n": top_n, "count": len(ranked),
                           "indices": [node.node.node_id for node in ranked], "seconds": elapsed})
            print(f"{language} top_n={top_n}: {checks[-1]['indices']} ({elapsed:.3f}s) PASS", flush=True)

        # Reconstruct the previous zip-based mapping to make the regression
        # visible with actual model scores, without changing production code.
        legacy_scores = [node.score for node in nodes]
        for i, (_, score) in enumerate(raw[:2]):
            legacy_scores[i] = score
        report["fixtures"].append({
            "language": language, "query": query, "texts": texts,
            "raw_pipeline_results": raw, "request_checks": checks,
            "legacy_top_2_scores_in_recall_order": legacy_scores,
            "expected_top_2": raw[:2],
        })

    report["status"] = "passed"
    report["total_seconds"] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"PASS: {args.output}", flush=True)


if __name__ == "__main__":
    main()
