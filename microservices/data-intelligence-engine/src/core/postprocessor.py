# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Postprocessing stage: reranking, and metadata replacement.

`postprocess_nodes` runs over a chunk set. Ported from
edgecraftrag/components/postprocessor.py:
RerankProcessor plus the postprocessor loop in components/pipeline.py:570. The
reranker uses the same provider names as embedding (config.MODEL_BACKENDS):

- "llamaindex_openvino" -> llama-index OpenVINORerank over a workspace model
- "openvino_genai"      -> OpenVINOGenAIReranking, same workspace models
- "openai_compatible"   -> an OpenAI-compatible `/rerank` endpoint
- "openvino_vl"         -> request-scoped Qwen VL postprocessor over a cached scorer

`run()` mirrors RerankProcessor.run(retri_res=..., query_bundle=...), with top_n
passed per call: the caller owns that setting, and the model instance is shared
across requests.

Models are cached by (backend, model path, device). EdgeCraftRAG keeps one
reranker for the lifetime of a pipeline; since pipelines live with the
caller now, the engine caches on the model identity instead -- otherwise every
request would recompile the OpenVINO model.
"""

import threading
from typing import Dict, List, Optional, Tuple

import config
from core.embedding import require_openvino_model
from llama_index.core.schema import NodeWithScore, QueryBundle


def postprocess_nodes(
    query: str,
    nodes: List[NodeWithScore],
    processor_type: str,
    top_n: Optional[int] = None,
    reranker_model=None,
) -> List[NodeWithScore]:
    """Run one postprocessing stage over a chunk set.

    `reranker_model` selects which reranker to use; the built model is cached
    below, so repeated requests do not recompile it.
    """
    if processor_type == "metadata_replace":
        for node in nodes:
            node.node.text = node.node.metadata.get("window", node.node.text)
        return nodes
    model = reranker_model.model_dump() if hasattr(reranker_model, "model_dump") else (reranker_model or {})
    reranker = build_reranker(
        top_n=top_n or config.RERANK_TOP_N,
        backend=model.get("backend"),
        model_id=model.get("model_id"),
        model_path=model.get("model_path"),
        device=model.get("device"),
        api_base=model.get("api_base"),
    )
    return reranker.run(retri_res=nodes, query_bundle=QueryBundle(query), top_n=top_n)


class _RemoteReranker:
    """Reranking over an OpenAI-compatible `/rerank` endpoint.

    vLLM (and other Cohere/Jina-style servers) take POST {model, query, documents,
    top_n} and answer {results: [{index, relevance_score}]}; Text Embeddings
    Inference takes `texts` instead of `documents` and answers a bare list of
    {index, score}. The request carries both field names and either response
    shape is accepted, so one provider covers both servers. Keeps the llama-index
    postprocessor interface so the caller cannot tell the difference.

    Stateless per call -- `top_n` is an argument, not written onto the instance --
    so concurrent requests need no lock; the server batches them itself.
    """

    def __init__(self, model_id: str, api_base: str, top_n: int):
        self.model_id = model_id
        self.api_base = (api_base or "").rstrip("/")
        self.top_n = top_n
        if not self.api_base:
            raise ValueError(
                "The 'openai_compatible' rerank provider needs an endpoint: "
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
        # A local model has top_n set on it before inference and drives a single
        # infer request; serialize the pair so concurrent requests with different
        # top_n cannot interleave. A remote reranker takes top_n per call and
        # holds no inference state, so it runs unlocked (serialize=False).
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
    model_path: Optional[str] = None,
    device: Optional[str] = None,
    backend: Optional[str] = None,
    api_base: Optional[str] = None,
    document_fn=None,
) -> RerankProcessor:
    """Return a reranker, reusing the compiled model for repeated requests.

    Unset arguments fall back to the engine's configured defaults; the caller (its
    retrieval pipeline) normally sends the model and device chosen by the user.
    The VL adapter is request-scoped because its document reader is request data.
    """
    top_n = top_n or config.RERANK_TOP_N
    if backend == "openvino_vl":
        if document_fn is None:
            raise ValueError("openvino_vl requires a media document reader")
        from core.embedding import resolve_model_path
        from inference.ov_adapter import OpenVINOVLReranker, OpenVINOVLReranking

        resolved = resolve_model_path(model_path or (
            # A picked workspace model addresses its own directory, exactly like
            # the text backends below; only the default id takes the default path.
            config.MEDIA_RERANK_MODEL_PATH if model_id in (None, config.MEDIA_RERANK_MODEL_ID)
            else model_id
        ))
        model_id = model_id or config.MEDIA_RERANK_MODEL_ID
        device = device or config.MEDIA_RERANK_DEVICE
        key = (backend, model_id, resolved, device)
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
    # A local backend addresses a model directory; the model chosen in the UI is a
    # name under the workspace's model directory, which is also a valid path here.
    model_path = model_path or (
        config.RERANK_MODEL_PATH if model_id == config.RERANK_MODEL_ID else model_id
    )
    device = device or config.RERANK_DEVICE
    api_base = api_base or config.RERANK_API_BASE

    key = (backend, model_id, model_path, device, api_base)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        # Re-check: another thread may have built it while we waited.
        cached = _CACHE.get(key)
        if cached is None:
            cached = _build(backend, top_n, model_id, model_path, device, api_base)
            _CACHE[key] = cached
    return cached


def _build(
    backend: str, top_n: int, model_id: str, model_path: str, device: str, api_base: str
) -> RerankProcessor:
    if backend == "openai_compatible":
        return RerankProcessor(_RemoteReranker(model_id, api_base, top_n), top_n, serialize=False)

    if backend == "llamaindex_openvino":
        resolved = require_openvino_model(model_path, "reranker")
        from llama_index.postprocessor.openvino_rerank import OpenVINORerank

        model = OpenVINORerank(
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

    if backend == "openvino_genai":
        resolved = require_openvino_model(model_path, "reranker")
        from inference.ov_adapter import OpenVINOGenAIReranking

        model = OpenVINOGenAIReranking(
            model_id_or_path=resolved, device=device, top_n=top_n
        )
        return RerankProcessor(model, top_n)

    raise ValueError(f"Rerank provider {backend!r} has no factory implementation")
