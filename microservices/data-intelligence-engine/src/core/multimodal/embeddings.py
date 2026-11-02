# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Multimodal embedding factory -- the same shape as `core/embeddings.py`.

One factory, cached per configuration, with every heavy import done lazily
inside its builder so importing this module costs nothing and needs no model.
That is deliberate symmetry: a source configures a multimodal model exactly the
way it configures a text one, and `MultimodalIndexer` is `VectorIndexer` with a
different `build_*` call.

**The contract a new model has to meet is `MultimodalEmbedding` below.** A
model that satisfies it drops in by being registered in
`core/multimodal/registry.py`; nothing else in the engine changes. Modalities
a model genuinely cannot do raise `NotImplementedError` rather than returning
something plausible -- X-CLIP has no single-image encoder and GME has no video
encoder, and a source is routed to one or the other by block kind, so the
unsupported call should never be reached. If it is, that is a routing bug and
it should say so loudly.
"""

from typing import Any, FrozenSet, List, Mapping, Optional, Protocol, Sequence, runtime_checkable

from inference.model_cache import ModelCache

#: One embedding. Plain floats, because this crosses into llama-index nodes and
#: a vector store, neither of which wants a framework's tensor type.
Vector = List[float]


@runtime_checkable
class MultimodalEmbedding(Protocol):
    """What a model must do to be a multimodal source's embedding model.

    Three requirements that are easy to get wrong and impossible to see going
    wrong, so they are stated here rather than left to each implementation:

    1. **`dimension` is declared, not probed.** The collection is created with
       it before anything is embedded, and probing would mean running a model
       that may take seconds to load and seconds more to run, once per source,
       to learn a constant the model card already states.
    2. **Vectors are L2-normalized on the way out.** The collections are built
       with an inner-product metric, where normalizing is what makes IP equal
       cosine. An un-normalized vector does not fail: it ranks subtly wrongly,
       which is the kind of defect that survives to production.
    3. **Text and media land in the same space.** A multimodal source exists so
       a text query can match a picture. `embed_text` must therefore be the
       model's *own* text tower, not some other text model.
    """

    dimension: int
    #: Block roles (`core.content.ROLE_*`) this model can embed. Declared here,
    #: on the model, because it is the only thing that knows: a projection and
    #: the coverage report both ask it, and nothing about it is written into
    #: stored content.
    supported_roles: FrozenSet[str]

    def embed_text(self, texts: Sequence[str]) -> List[Vector]:
        """One vector per text, in the model's shared space."""

    def embed_image(self, images: Sequence[Any]) -> List[Vector]:
        """One vector per PIL image."""

    def embed_video(self, frames: Sequence[Any]) -> Vector:
        """**One** vector for one clip, given its sampled frames.

        Not one per frame: a clip is a thing, and a projection that wrote a
        vector per frame would make the number of records depend on the video's
        length, which is what "do not chunk a short video" rules out.
        """


# Weak: a model lives as long as some projection holds it (inference/model_cache.py).
_CACHE = ModelCache()


def build_multimodal_embedding(
    record: Mapping[str, Any], options: Optional[Mapping[str, Any]] = None
) -> MultimodalEmbedding:
    """The model a multimodal source's profile recorded, built at most once.

    Cached like `core/embeddings.py:build_embedding`, and for the same reason:
    loading one of these is expensive and several sources usually share it.
    Checking its prepared artifacts and fixed inputs is the registry's job
    (`core/multimodal/registry.py:load`); no model is downloaded or exported.
    """
    from core.multimodal import registry

    options = dict(options or {})
    key = (
        record.get("name"),
        record.get("path"),
        options.get("embedding_device"),
        tuple(sorted((k, options[k]) for k in registry.MODEL_PARAMS if k in options)),
    )
    return _CACHE.get_or_build(key, lambda: registry.load(record, options))


def supported_roles(name: str) -> FrozenSet[str]:
    """Which roles a registered model embeds, without loading it."""
    from core.multimodal import registry

    model = next((m for m in registry.MODELS if m.name == name), None)
    return model.supported_roles if model is not None else frozenset()


def normalize(vector: Sequence[float]) -> Vector:
    """`vector` scaled to unit length, or left alone if it has none.

    Every backend ends with this, so the normalization requirement in
    `MultimodalEmbedding` is met in one place instead of being re-derived (and
    occasionally forgotten) per model.
    """
    total = sum(value * value for value in vector) ** 0.5
    if total <= 0:
        return [float(value) for value in vector]
    return [float(value) / total for value in vector]


__all__ = [
    "MultimodalEmbedding",
    "Vector",
    "build_multimodal_embedding",
    "normalize",
    "supported_roles",
]
