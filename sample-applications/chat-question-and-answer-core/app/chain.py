from .config import config
from .utils import login_to_huggingface, download_huggingface_model, convert_model
from .document import load_file_document
from .logger import logger
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import OpenVINOBgeEmbeddings
from langchain_community.document_compressors.openvino_rerank import OpenVINOReranker
from langchain.retrievers import ContextualCompressionRetriever
from langchain_huggingface import HuggingFacePipeline
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
import os
import pandas as pd

vectorstore = None

# The RUN_TEST flag is used to bypass the model download and conversion steps during pytest unit testing.
# If RUN_TEST is set to "True", the model download and conversion steps are skipped.
# This flag is set in the conftest.py file before running the tests.
if os.getenv("RUN_TEST", "").lower() != "true":
    # login huggingface
    login_to_huggingface(config.HF_ACCESS_TOKEN)

    # Download convert the model to openvino optimized
    download_huggingface_model(config.EMBEDDING_MODEL_ID, config._CACHE_DIR)
    download_huggingface_model(config.RERANKER_MODEL_ID, config._CACHE_DIR)
    download_huggingface_model(config.LLM_MODEL_ID, config._CACHE_DIR)

    # Convert to openvino IR
    convert_model(config.EMBEDDING_MODEL_ID, config._CACHE_DIR, "embedding")
    convert_model(config.RERANKER_MODEL_ID, config._CACHE_DIR, "reranker")
    convert_model(config.LLM_MODEL_ID, config._CACHE_DIR, "llm")


    template = config.PROMPT_TEMPLATE

    prompt = ChatPromptTemplate.from_template(template)

    # Initialize Embedding Model
    embedding = OpenVINOBgeEmbeddings(
        model_name_or_path=f"{config._CACHE_DIR}/{config.EMBEDDING_MODEL_ID}",
        model_kwargs={"device": config.EMBEDDING_DEVICE, "compile": False},
    )
    embedding.ov_model.compile()

    # Initialize Reranker Model
    reranker = OpenVINOReranker(
        model_name_or_path=f"{config._CACHE_DIR}/{config.RERANKER_MODEL_ID}",
        model_kwargs={"device": config.RERANKER_DEVICE},
        top_n=2,
    )

    # Initialize LLM
    llm = HuggingFacePipeline.from_model_id(
        model_id=f"{config._CACHE_DIR}/{config.LLM_MODEL_ID}",
        task="text-generation",
        backend="openvino",
        model_kwargs={
            "device": config.LLM_DEVICE,
            "ov_config": {
                "PERFORMANCE_HINT": "LATENCY",
                "NUM_STREAMS": "1",
                "CACHE_DIR": f"{config._CACHE_DIR}/{config.LLM_MODEL_ID}/model_cache",
            },
            "trust_remote_code": True,
        },
        pipeline_kwargs={"max_new_tokens": config.MAX_TOKENS},
    )
    if llm.pipeline.tokenizer.eos_token_id:
        llm.pipeline.tokenizer.pad_token_id = llm.pipeline.tokenizer.eos_token_id
else:
    logger.info("Bypassing to mock these functions because RUN_TEST is set to 'True' to run pytest unit test.")


def default_context(docs):
    """
    Returns a default context when the retriever is None.

    This function is used to provide a default context in scenarios where
    the retriever is not available or not provided.

    Returns:
        str: An empty string as the default context.
    """

    return ""


def get_retriever(enable_rerank=True, search_method="similarity_score_threshold"):
    """
    Creates and returns a retriever object with optional reranking capability.

    Args:
        enable_rerank (bool): If True, enables the reranker to improve retrieval results. Defaults to True.
        search_method (str): The method used for searching within the vector store. Defaults to "similarity_score_threshold".

    Returns:
        retriever: A retriever object, optionally wrapped with a contextual compression reranker.

    """

    if vectorstore == None:
        return None

    else:
        retriever = vectorstore.as_retriever(
            search_kwargs={"k": 3, "score_threshold": 0.5}, search_type=search_method
        )
        if enable_rerank:
            logger.info("Enable reranker")

            return ContextualCompressionRetriever(
                base_compressor=reranker, base_retriever=retriever
            )
        else:
            logger.info("Disable reranker")

            return retriever


def build_chain(retriever=None):
    """
    Builds a Retrieval-Augmented Generation (RAG) chain using the provided retriever.

    Args:
        retriever: A retriever object that fetches relevant documents based on a query.

    Returns:
        A RAG chain that processes the context and question, and generates a response.
    """

    if retriever:
        context = retriever | (
            lambda docs: "\n\n".join(doc.page_content for doc in docs)
        )
    else:
        context = default_context

    chain = (
        {
            "context": context,
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain


async def process_query(chain=None, query: str = ""):
    """
    Processes a query using the provided chain and yields the results asynchronously.
    Args:
        chain: An optional chain object that has an `astream` method to process the query.
        query (str): The query string to be processed.
    Yields:
        str: The processed data chunks in the format "data: {chunk}\n\n".
    """

    async for chunk in chain.astream(query):
        yield f"data: {chunk}\n\n"


def create_faiss_vectordb(file_path: str = "", chunk_size=1000, chunk_overlap=200):
    """
    Creates a FAISS vector database from a document file.
    This function loads a document from the specified file path, splits it into chunks,
    creates embeddings for the chunks, and stores them in a FAISS vector database. If a
    global vectorstore already exists, it merges the new embeddings into the existing
    vectorstore.

    Args:
        file_path (str): The path to the document file. Defaults to an empty string.
        chunk_size (int): The size of each chunk in characters. Defaults to 1000.
        chunk_overlap (int): The number of overlapping characters between chunks. Defaults to 200.

    Returns:
        bool: True if the vector database was created successfully.
    """

    global vectorstore
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    # Load the document from the /tmp path and create embedding
    docs = load_file_document(file_path)
    splits = text_splitter.split_documents(docs)

    if not splits:
        logger.error("No text data from the document.")
        return False

    doc_embedding = FAISS.from_documents(documents=splits, embedding=embedding)
    if vectorstore == None:
        vectorstore = doc_embedding
    else:
        vectorstore.merge_from(doc_embedding)

    return True


def get_document_from_vectordb():
    """
    Retrieve document names from the vector database.
    This function accesses the global `vectorstore` object, extracts document
    metadata, and returns a list of document names.

    Returns:
        []: Return empty list if the `vectorstore` is None.
        list: A list of document names extracted from the vector database.
    """

    global vectorstore

    if vectorstore is None:
        return []

    vstore = vectorstore.docstore._dict

    docs = {vstore[key].metadata["source"].split("/")[-1] for key in vstore.keys()}

    return list(docs)


def delete_embedding_from_vectordb(document: str = "", delete_all: bool = False):
    """
    Deletes embeddings from the vector database.

    Args:
        document (str): The name of the document whose embeddings are to be deleted. If empty, no specific document is targeted.
        delete_all (bool): If True, all embeddings in the vector database will be deleted. If False, only embeddings related to the specified document will be deleted.

    Returns:
        bool: True if the deletion process completes successfully.
    """

    global vectorstore

    if vectorstore is None:
        return False

    vstore = vectorstore.docstore._dict
    data_rows = []

    for key in vstore.keys():
        doc_name = vstore[key].metadata["source"].split("/")[-1]
        content = vstore[key].page_content
        data_rows.append(
            {
                "chunk_id": key,
                "document": doc_name,
                "content": content,
            }
        )

    vectordf = pd.DataFrame(data_rows)

    if delete_all:
        # delete all the embeddings in vectorstore
        chunk_list = vectordf["chunk_id"].tolist()
    else:
        # delete the specified document embeddings in vectorstore
        chunk_list = vectordf.loc[vectordf["document"] == document]["chunk_id"].tolist()

    vectorstore.delete(chunk_list)

    return True
