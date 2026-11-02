# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from urllib.parse import urlparse
from typing import TYPE_CHECKING, List
import requests
from langchain_core.embeddings import Embeddings

from src.common.logger import get_logger
from src.common.settings import settings

if TYPE_CHECKING:
    from src.common.schema import ImageInput


logger = get_logger()


def should_use_no_proxy(url: str) -> bool:
    """Return True when the URL host matches configured no_proxy domains."""
    no_proxy = settings.no_proxy
    hostname = urlparse(url).hostname
    if not hostname or not no_proxy:
        return False
    for domain in no_proxy.split(","):
        normalized = domain.strip()
        if normalized and hostname.endswith(normalized):
            return True
    return False


class EmbeddingAPI(Embeddings):
    """Embedding client that delegates vector generation to a remote API."""

    def __init__(self, api_url: str, model_name: str) -> None:
        """Initialize embedding API client settings."""
        self.api_url = api_url.rstrip("/")
        self.model_name = model_name
        self._embedding_length: int | None = None

    def _post_embeddings(self, payload: dict) -> List[List[float]]:
        """Send embedding request payload and normalize response shape."""
        # Use empty-string proxies to explicitly bypass (proxies=None would
        # fall back to env-var resolution where uppercase NO_PROXY may not
        # include Docker service hostnames).
        proxies = (
            {"http": "", "https": ""}
            if should_use_no_proxy(self.api_url)
            else {"http": settings.http_proxy, "https": settings.https_proxy}
        )

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                proxies=proxies,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            embeddings = response.json().get("embedding")
            if not isinstance(embeddings, list):
                raise ValueError("Embedding service returned unexpected payload")
            if embeddings and isinstance(embeddings[0], (int, float)):
                embeddings = [embeddings]
            return embeddings
        except requests.RequestException as exc:
            logger.error("Failed to call embedding service: %s", exc)
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of document strings."""
        payload = {
            "model": self.model_name,
            "input": {"type": "text", "text": texts},
            "encoding_format": "float",
        }
        return self._post_embeddings(payload)

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a single query string."""
        payload = {
            "model": self.model_name,
            "input": {"type": "text", "text": text},
            "encoding_format": "float",
        }
        embeddings = self._post_embeddings(payload)
        return embeddings[0]

    def embed_image_url(self, url: str) -> List[float]:
        """Generate embedding for an image specified by URL."""
        payload = {
            "model": self.model_name,
            "input": {"type": "image_url", "image_url": url},
            "encoding_format": "float",
        }
        embeddings = self._post_embeddings(payload)
        return embeddings[0]

    def embed_image_base64(self, data: str) -> List[float]:
        """Generate embedding for a base64-encoded image."""
        payload = {
            "model": self.model_name,
            "input": {"type": "image_base64", "image_base64": data},
            "encoding_format": "float",
        }
        embeddings = self._post_embeddings(payload)
        return embeddings[0]

    def embed_image(self, image: ImageInput) -> List[float]:
        """Generate embedding for an image input (URL or base64)."""
        if image.type == "image_url":
            return self.embed_image_url(image.image_url)
        return self.embed_image_base64(image.image_base64)

    def get_embedding_length(self) -> int:
        """Resolve and cache embedding vector dimensionality."""
        if self._embedding_length is not None:
            return self._embedding_length
        sample_embedding = self.embed_documents(["probe_text"])
        if not sample_embedding or not isinstance(sample_embedding[0], list):
            raise ValueError("Embedding service returned invalid probe response")
        self._embedding_length = len(sample_embedding[0])
        return self._embedding_length
