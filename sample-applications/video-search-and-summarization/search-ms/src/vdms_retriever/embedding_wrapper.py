# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from langchain_core.embeddings import Embeddings
import requests
from typing import List
from src.utils.common import logger, settings
from urllib.parse import urlparse

def should_use_no_proxy(url: str) -> bool:
    no_proxy = settings.no_proxy_env
    hostname = urlparse(url).hostname
    logger.debug(
        f"Checking no_proxy for hostname: {hostname} against no_proxy domains: {no_proxy}"
    )
    if hostname:
        for domain in no_proxy.split(","):
            domain = domain.strip()
            if not domain:
                continue
            if hostname.endswith(domain):
                logger.debug(f"Hostname {hostname} matches no_proxy domain {domain}")
                return True
    return False


class EmbeddingAPI(Embeddings):
    """Lightweight embedding client that forwards text requests to the serving API."""

    def __init__(self, api_url: str, model_name: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.model_name = model_name

    def _post_embeddings(self, payload: dict) -> List[List[float]]:
        """Execute a POST request to the embedding service."""
        proxies = (
            None
            if should_use_no_proxy(self.api_url)
            else {"http": settings.http_proxy, "https": settings.https_proxy}
        )

        try:
            response = requests.post(self.api_url, json=payload, proxies=proxies)
            logger.debug("Embedding service response status code: %s", response.status_code)
            response.raise_for_status()
            embeddings = response.json()["embedding"]
            if not isinstance(embeddings, list):
                raise ValueError("Embedding service returned unexpected payload")
            if embeddings and isinstance(embeddings[0], (int, float)):
                embeddings = [embeddings]
            return embeddings
        except requests.RequestException as exc:
            logger.error("Failed to call embedding service: %s", exc)
            raise Exception("Error creating embedding") from exc

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        logger.debug("Embedding batch of %d documents", len(texts))
        payload = {
            "model": self.model_name,
            "input": {"type": "text", "text": texts},
            "encoding_format": "float",
        }
        return self._post_embeddings(payload)

    def embed_query(self, text: str) -> List[float]:
        logger.debug("Embedding single query")
        payload = {
            "model": self.model_name,
            "input": {"type": "text", "text": text},
            "encoding_format": "float",
        }
        embeddings = self._post_embeddings(payload)
        return embeddings[0]

    def get_embedding_length(self) -> int:
        logger.debug(
            "Retrieving embedding dimensionality for model %s via API probe", self.model_name
        )
        if settings.EMBEDDING_LENGTH > 0:
            return settings.EMBEDDING_LENGTH

        sample_embedding = self.embed_documents(["probe_text"])
        if not sample_embedding or not isinstance(sample_embedding[0], list):
            raise ValueError("Embedding service returned invalid probe response")

        settings.EMBEDDING_LENGTH = len(sample_embedding[0])
        logger.debug("Embedding dimension detected: %d", settings.EMBEDDING_LENGTH)
        return settings.EMBEDDING_LENGTH
