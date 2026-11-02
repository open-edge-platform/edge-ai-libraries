# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unified cross-media reranking over authorized retrieval results.

One model scores every media group's candidates together, so the merged list
ranks globally by the final `score` (DEC-01). The local model is cached by
identity. Inference is serialized because a single OpenVINO infer request and
its processor cannot be used concurrently.
"""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import logging

import config
from core.content import is_file_uri
from core.file_asset_library import chunks_to_nodes, nodes_to_chunks
from core.postprocessor import build_reranker
from llama_index.core.schema import QueryBundle


logger = logging.getLogger(__name__)


def build_media_reranker(options, document_fn, top_n):
    """Resolve every omitted request field against media, never text, defaults."""
    selected = options.reranker_model if options else None
    model = selected.model_dump(exclude_none=True) if selected else {}
    backend = model.get("backend") or config.MEDIA_RERANK_BACKEND
    if backend != "openvino_vl":
        raise ValueError(f"media reranking backend {backend!r} is unavailable")
    model_id = model.get("model_id") or config.MEDIA_RERANK_MODEL_ID
    model_path = model.get("model_path") or (
        config.MEDIA_RERANK_MODEL_PATH
        if model_id == config.MEDIA_RERANK_MODEL_ID
        else model_id
    )
    device = model.get("device") or config.MEDIA_RERANK_DEVICE
    return build_reranker(
        backend=backend, model_id=model_id, model_path=model_path, device=device,
        top_n=top_n, document_fn=document_fn,
    )


def _document(hit, target, library):
    if target in ("audio", "document"):
        # The indexed unit is an ASR window; the transcript is already in text.
        if not hit.text.strip():
            raise ValueError(f"{target} candidate has no text for reranking")
        return {"text": hit.text}
    key = hit.metadata.get("media_key")
    if not key:
        raise KeyError("media_key")
    source_id = hit.metadata.get("source_id")
    if target == "image":
        from PIL import Image

        data = library.blob_reader()(key, source_id)
        with Image.open(BytesIO(data)) as image:
            return {"image": image.convert("RGB")}
    if target == "video":
        from core.multimodal import frames
        from inference.multimodal.qwen3_vl_reranker_inputs import pad_frames

        # A fixed frame count keeps the compiled video graph shape-constant.
        if is_file_uri(key):
            path = library.blob_file_path(key, source_id)
            return {"video": pad_frames(
                frames.sample_frames(path, config.MEDIA_RERANK_VIDEO_MAX_FRAMES),
                config.MEDIA_RERANK_VIDEO_MAX_FRAMES,
            )}
        data = library.blob_reader()(key, source_id)
        path = frames.materialize(data)
        try:
            return {"video": pad_frames(
                frames.sample_frames(path, config.MEDIA_RERANK_VIDEO_MAX_FRAMES),
                config.MEDIA_RERANK_VIDEO_MAX_FRAMES,
            )}
        finally:
            frames.discard(path)
    raise ValueError(f"unsupported media target {target!r}")


def rerank_media(query, groups, options, top_k, *, strict=False):
    """Score every group's candidates together and return the global top-k.

    `groups` is a list of (target, candidates, library) triples. Unreadable
    media is removed under the same asset-visibility rule as /v1/blob unless
    `strict` requests an error for any unreadable candidate. Scores
    are committed only after *all* retained candidates were scored: on any
    failure this returns (None, "degraded") and the caller falls the whole
    request back to the original per-media recall order, so ANN scores and
    rerank scores never mix in one ranking.
    """
    # Loading a candidate's media (blob reads, video decode) outweighs the
    # scoring itself and has no cross-candidate dependency, so load in
    # parallel. pool.map keeps submission order, which is what document_fn's
    # positional indexing below relies on.
    work = [
        (hit, target, library)
        for target, candidates, library in groups
        for hit in candidates
    ]

    def load(item):
        hit, target, library = item
        try:
            return _document(hit, target, library)
        except (KeyError, OSError, PermissionError, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=config.MEDIA_RERANK_DOC_WORKERS) as pool:
        loaded = list(pool.map(load, work))
    if strict and any(document is None for document in loaded):
        raise ValueError("one or more retrieved media candidates cannot be read for reranking")
    hits = []
    documents = []
    for (hit, _, _), document in zip(work, loaded):
        if document is None:
            continue
        hits.append(hit.model_copy(deep=True))
        documents.append(document)
    if not hits:
        return [], "ok"

    nodes = chunks_to_nodes(hits)

    def document_fn(index, _node):
        return documents[index]

    try:
        processor = build_media_reranker(options, document_fn, top_k)
        ranked = processor.run(nodes, query_bundle=QueryBundle(query), top_n=top_k)
    except Exception:
        logger.exception("unified media reranking failed")
        return None, "degraded"
    return nodes_to_chunks(ranked), "ok"
