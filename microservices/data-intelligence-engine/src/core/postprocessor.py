# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import threading
from typing import Dict, List, Optional, Tuple

import config
from core.embedding import require_openvino_model, resolve_model_path
from inference.meta import InferenceMeta
from llama_index.core.schema import NodeWithScore, QueryBundle

logger = logging.getLogger(__name__)


def reranker_class(backend: Optional[str], model_id: Optional[str]):
    """The class a reranker request resolves to: a Qwen VL export is the media one."""
    from inference.models import _qwen3_vl_reranker_ready

    if backend and config.normalize_model_backend(backend) == config.REMOTE_OPENAI_COMPATIBLE:
        return _RemoteReranker
    if model_id and _qwen3_vl_reranker_ready(resolve_model_path(model_id)):
        from inference.ov_adapter import OpenVINOVLReranker

        return OpenVINOVLReranker
    from inference.ov_adapter import OpenVINOGenAIReranking

    return OpenVINOGenAIReranking


def is_media_reranker(model_id: Optional[str]) -> bool:
    """Whether this model reranks media, not just text."""
    return reranker_class(None, model_id).SUPPORT_MULTIMODAL is True


def postprocess_nodes(
    query: str,
    nodes: List[NodeWithScore],
    processor_type: str,
    top_n: Optional[int] = None,
    reranker_model=None,
) -> List[NodeWithScore]:
    """Rerank a chunk set."""
    model = reranker_model.model_dump() if hasattr(reranker_model, "model_dump") else (reranker_model or {})
    reranker = build_reranker(
        top_n=top_n or config.RERANK_TOP_N,
        backend=model.get("backend"),
        model_id=model.get("model_id"),
        device=model.get("device"),
        api_base=model.get("api_base"),
    )
    return reranker.run(retri_res=nodes, query_bundle=QueryBundle(query), top_n=top_n)


class _RemoteReranker(InferenceMeta):
    """Reranking over an OpenAI-compatible `/rerank` endpoint (vLLM/Cohere/Jina style or TEI)."""

    BACKEND = config.REMOTE_OPENAI_COMPATIBLE
    SUPPORT_MULTIMODAL = False

    def __init__(self, model_id: str, api_base: str, top_n: int):
        self.model_id = model_id
        self.api_base = (api_base or "").rstrip("/")
        self.top_n = top_n
        if not self.api_base:
            raise ValueError(
                "The 'remote_openai_compatible' rerank backend needs an endpoint: "
                "set ENGINE_RERANK_API_BASE"
            )

    def postprocess_nodes(self, nodes, query_bundle=None, query_str=None, top_n=None):
        import httpx

        top_n = top_n or self.top_n
        query = query_str or (query_bundle.query_str if query_bundle else "")
        documents = [node.node.get_content() for node in nodes]
        if not documents:
            return []
        url = self.api_base if self.api_base.endswith("/rerank") else f"{self.api_base}/rerank"
        headers = {"Authorization": f"Bearer {config.RERANK_API_KEY}"} if config.RERANK_API_KEY else {}
        response = httpx.post(
            url,
            json={"model": self.model_id, "query": query, "documents": documents,
                  "texts": documents, "top_n": top_n},
            headers=headers,
            timeout=config.REMOTE_RERANK_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            results = payload
        else:
            results = payload.get("results") or payload.get("data") or []
        ranked = []
        for entry in results:
            index = entry.get("index")
            if not isinstance(index, int) or not 0 <= index < len(nodes):
                continue
            node = nodes[index]
            score = entry.get("relevance_score", entry.get("score"))
            ranked.append(NodeWithScore(node=node.node, score=float(score) if score is not None else node.score))
        # TEI ignores `top_n`, and not every server sorts: order and cut here.
        ranked.sort(key=lambda item: item.score if item.score is not None else float("-inf"), reverse=True)
        ranked = ranked[:top_n]
        if not ranked:
            raise ValueError(f"Reranker at {url} returned no usable results: {payload}")
        return ranked


class RerankProcessor:
    def __init__(self, rerank_model, top_n: int, serialize: bool = True, lock=None):
        self.model = rerank_model
        self.top_n = top_n
        self.default_top_n = top_n
        # Local models get top_n set on the instance, so setting it and inferring must be serialized.
        self._lock = lock if lock is not None else (threading.Lock() if serialize else None)

    def run(
        self,
        retri_res: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
        query_str: Optional[str] = None,
        top_n: Optional[int] = None,
    ) -> List[NodeWithScore]:
        effective_top_n = top_n or self.default_top_n
        if self._lock is None:
            return self.model.postprocess_nodes(
                retri_res, query_bundle=query_bundle, query_str=query_str, top_n=effective_top_n
            )
        with self._lock:
            if hasattr(self.model, "top_n"):
                self.model.top_n = effective_top_n
            return self.model.postprocess_nodes(retri_res, query_bundle=query_bundle, query_str=query_str)


_CACHE: Dict[Tuple, RerankProcessor] = {}
_VL_CACHE: Dict[Tuple, Tuple[object, threading.Lock]] = {}
_CACHE_LOCK = threading.Lock()


def build_reranker(
    top_n: int = None,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    backend: Optional[str] = None,
    api_base: Optional[str] = None,
    document_fn=None,
) -> RerankProcessor:
    """Return a reranker, reusing the compiled model for repeated requests."""
    top_n = top_n or config.RERANK_TOP_N
    if document_fn is not None:
        # Media reranker: request-scoped adapter over a cached scorer.
        if backend and config.normalize_model_backend(backend) != config.LOCAL_OPENVINO:
            raise ValueError("media reranking runs on the local_openvino backend")
        from inference.ov_adapter import OpenVINOVLReranker, OpenVINOVLReranking

        model_id = model_id or config.MEDIA_RERANK_MODEL_ID
        resolved = resolve_model_path(model_id)
        device = device or config.MEDIA_RERANK_DEVICE
        key = (config.LOCAL_OPENVINO, model_id, resolved, device)
        shared = _VL_CACHE.get(key)
        if shared is None:
            with _CACHE_LOCK:
                shared = _VL_CACHE.get(key)
                if shared is None:
                    shared = (OpenVINOVLReranking(resolved, device=device), threading.Lock())
                    _VL_CACHE[key] = shared
        adapter = OpenVINOVLReranker(
            model_id_or_path=resolved,
            top_n=top_n,
            scorer=shared[0],
            document_fn=document_fn,
        )
        return RerankProcessor(adapter, top_n, lock=shared[1])

    backend = config.normalize_model_backend(backend or config.RERANK_BACKEND)
    model_id = model_id or config.RERANK_MODEL_ID
    device = device or config.RERANK_DEVICE
    api_base = api_base or config.RERANK_API_BASE

    key = (backend, model_id, device, api_base)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            cached = _build(backend, top_n, model_id, device, api_base)
            _CACHE[key] = cached
    return cached


def _build(
    backend: str, top_n: int, model_id: str, device: str, api_base: str
) -> RerankProcessor:
    if backend == config.REMOTE_OPENAI_COMPATIBLE:
        return RerankProcessor(_RemoteReranker(model_id, api_base, top_n), top_n, serialize=False)

    resolved = require_openvino_model(model_id, "reranker")
    from inference.ov_adapter import OpenVINOGenAIReranking, llamaindex_openvino_rerank

    try:
        # The exported graph needs fixed-length input within the model's position limit.
        model = OpenVINOGenAIReranking(
            model_id_or_path=resolved,
            device=device,
            top_n=top_n,
            max_length=config.embedding_max_length(resolved),
            pad_to_max_length=True,
            padding_side="right",
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "ov_genai reranker failed for %s; falling back to ov_llamaindex",
            resolved, exc_info=True,
        )
        model = llamaindex_openvino_rerank(
            model_id_or_path=resolved,
            device=device,
            top_n=top_n,
            model_kwargs={
                "ov_config": dict(config.OPENVINO_CONFIG),
                "local_files_only": True,
                "export": False,
            },
        )
    return RerankProcessor(model, top_n)
