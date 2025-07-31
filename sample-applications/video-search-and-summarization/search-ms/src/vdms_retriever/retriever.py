# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from langchain_community.vectorstores.vdms import VDMS, VDMS_Client

from src.utils.common import settings
from src.vdms_retriever.embedding_wrapper import vCLIPEmbeddingsWrapper

DEBUG = False
client = VDMS_Client(settings.VDMS_VDB_HOST, settings.VDMS_VDB_PORT)


def get_vectordb() -> VDMS:
    """
    Initializes and returns a vector database based on the specified configuration.
    Depending on the configuration, it uses either CLIP embeddings, a HuggingFace endpoint for embeddings,
    or a default HuggingFace BGE embeddings model.
    Returns:
        tuple: The vector database instance
    """

    embeddings = vCLIPEmbeddingsWrapper(
        api_url=settings.VCLIP_EMBEDDINGS_ENDPOINT,
        model_name=settings.VCLIP_EMBEDDINGS_MODEL_NAME,
        num_frames=settings.VCLIP_EMBEDDINGS_NUM_FRAMES,
    )

    vector_dimensions = embeddings.get_embedding_length()

    vector_db = VDMS(
        client=client,
        embedding=embeddings,
        collection_name=settings.INDEX_NAME,
        distance_strategy=settings.DISTANCE_STRATEGY,
        embedding_dimensions=vector_dimensions,
        engine=settings.SEARCH_ENGINE,
    )

    return vector_db
