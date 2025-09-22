# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any, Dict

import requests

logging.basicConfig(level=logging.INFO)


class CustomReranker:
    def __init__(self, reranking_endpoint: str):
        self._reranking_endpoint = reranking_endpoint
        logging.info(
            f"Initialized CustomReranker with reranking_endpoint: {self._reranking_endpoint}"
        )

    @property
    def reranking_endpoint(self) -> str:
        return self._reranking_endpoint

    @reranking_endpoint.setter
    def reranking_endpoint(self, value: str):
        self._reranking_endpoint = value

    def validate_retrieved_docs(self, retrieved_docs: Dict[str, Any]):
        if "question" not in retrieved_docs:
            raise ValueError("Question is required")
        if "context" not in retrieved_docs:
            raise ValueError("Context is required for reranker")

    def rerank(self, retrieved_docs: Dict[str, Any]) -> Dict[str, Any]:
        self.validate_retrieved_docs(retrieved_docs=retrieved_docs)
        if len(retrieved_docs["context"]) > 0:
            return self.rerank_tei(retrieved_docs=retrieved_docs)
        else:
            return retrieved_docs

    def rerank_tei(self, retrieved_docs: Dict[str, Any]) -> Dict[str, Any]:
        texts = map(lambda x: x.page_content, retrieved_docs["context"])
        texts = list(texts)

        request_body = {
            "query": retrieved_docs["question"],
            "texts": texts,
            "raw_scores": False,
        }

        response = requests.post(
            url=f"{self.reranking_endpoint}",
            json=request_body,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code == 200:
            res = response.json()
            # Sort results by score in descending order
            sorted_results = sorted(res, key=lambda x: x["score"], reverse=True)
            # Take top 3 results or all if less than 3
            top_k = min(3, len(sorted_results))
            reranked_context = [
                retrieved_docs["context"][item["index"]] for item in sorted_results[:top_k]
            ]            
            return {
                "question": retrieved_docs["question"],
                "context": reranked_context,
            }
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")
