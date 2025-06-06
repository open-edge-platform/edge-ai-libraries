from langchain_community.vectorstores.vdms import VDMS, VDMS_Client

# from .vCLIP import vCLIP
from src.utils.common import settings
from src.vdms_retriever.embedding_wrapper import vCLIPEmbeddingsWrapper

DEBUG = False
client = VDMS_Client(settings.VDMS_VDB_HOST, settings.VDMS_VDB_PORT)


def get_vectordb():
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
    dimensions = embeddings.get_embedding_length()
    vector_db = VDMS(
        client=client,
        embedding=embeddings,
        collection_name=settings.INDEX_NAME,
        embedding_dimensions=dimensions,
        distance_strategy=settings.DISTANCE_STRATEGY,
        engine=settings.SEARCH_ENGINE,
    )

    return vector_db
