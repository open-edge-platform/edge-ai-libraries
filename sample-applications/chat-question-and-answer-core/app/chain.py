from .config import config
from .document import load_file_document
from .logger import logger
from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from starlette.concurrency import run_in_threadpool
import os
import json
import importlib
import pandas as pd

vectorstore = None

# The RUN_TEST flag is used to bypass the model download and conversion steps during pytest unit testing.
# If RUN_TEST is set to "True", the model download and conversion steps are skipped.
# This flag is set in the conftest.py file before running the tests.
if os.getenv("RUN_TEST", "").lower() != "true":
    if config.MODEL_RUNTIME == "openvino":
        runtime_module = importlib.import_module("app.openvino_backend")
        runtime_instance = runtime_module.OpenVINOBackend()

    elif config.MODEL_RUNTIME == "ollama":
        runtime_module = importlib.import_module("app.ollama_backend")
        runtime_instance = runtime_module.OllamaBackend()

    else:
        raise ValueError(f"Unsupported model runtime: {config.MODEL_RUNTIME}")

    embedding, llm, reranker = runtime_instance.init_models()

    template = config.PROMPT_TEMPLATE

    prompt = ChatPromptTemplate.from_template(template)

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


def get_retriever():
    """
    Creates and returns a retriever object with optional reranking capability.

    Returns:
        retriever: A retriever object, optionally wrapped with a contextual compression reranker.

    """

    enable_rerank = config._ENABLE_RERANK
    logger.info(f"Reranker enabled: {enable_rerank}")
    search_method = config._SEARCH_METHOD
    fetch_k = config._FETCH_K

    if vectorstore == None:
        return None

    else:
        retriever = vectorstore.as_retriever(
            search_kwargs={
                "k": 3,
                "fetch_k": fetch_k,
            },
            search_type=search_method
        )
        if enable_rerank:
            return ContextualCompressionRetriever(
                base_compressor=reranker, base_retriever=retriever
            )
        else:
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


def retrieve_documents(query: str):
    """
    Retrieves the context documents for a query, keeping their metadata.

    The reranker returns new documents that carry only the index of the input document
    (`id`) and a `relevance_score`, so the original metadata (`source`, `page`, ...) is
    restored from the base retriever results.

    Args:
        query (str): The question text.

    Returns:
        list[Document]: Context documents in rank order, each with a `relevance_score`
        in its metadata when reranking is enabled.
    """

    if vectorstore is None:
        return []

    base_retriever = vectorstore.as_retriever(
        search_kwargs={"k": 3, "fetch_k": config._FETCH_K},
        search_type=config._SEARCH_METHOD,
    )
    candidates = base_retriever.invoke(query)

    if not config._ENABLE_RERANK or not candidates:
        return list(candidates)

    reranked = reranker.compress_documents(candidates, query)
    results = []
    for doc in reranked:
        idx = doc.metadata.get("id")
        original = candidates[idx] if isinstance(idx, int) and 0 <= idx < len(candidates) else doc
        metadata = dict(original.metadata)
        if "relevance_score" in doc.metadata:
            metadata["relevance_score"] = float(doc.metadata["relevance_score"])
        results.append(Document(page_content=original.page_content, metadata=metadata))

    return results


def format_labelled_context(docs) -> str:
    """
    Formats context documents as numbered sources `[S1]..[Sn]` for the prompt.

    Args:
        docs (list[Document]): Context documents in rank order.

    Returns:
        str: The labelled context string.
    """

    blocks = []
    for n, doc in enumerate(docs, start=1):
        header = f"[S{n}]"
        source = os.path.basename(str(doc.metadata.get("source", "")))
        if source:
            header += f" {source}"
        page = _page_label(doc.metadata)
        if page is not None:
            header += f", page {page}"
        blocks.append(f"{header}\n{doc.page_content}")

    return "\n\n".join(blocks)


def _page_label(metadata: dict):
    if metadata.get("page_label") not in (None, ""):
        return str(metadata["page_label"])
    if isinstance(metadata.get("page"), int):
        return str(metadata["page"] + 1)
    return None


def build_sources(docs) -> list:
    """
    Builds the `sources` list returned with an answer.

    Args:
        docs (list[Document]): Context documents in the same order as in the prompt.

    Returns:
        list[dict]: One entry per source with `id` (S1..Sn), `source` (file name),
        `page` (0-based, as set by the loader, or None), `page_label`, `snippet` and
        `relevance_score` (None when reranking is disabled).
    """

    sources = []
    for n, doc in enumerate(docs, start=1):
        page = doc.metadata.get("page")
        score = doc.metadata.get("relevance_score")
        sources.append(
            {
                "id": f"S{n}",
                "source": os.path.basename(str(doc.metadata.get("source", ""))),
                "page": page if isinstance(page, int) else None,
                "page_label": _page_label(doc.metadata),
                "snippet": doc.page_content[: config.SOURCE_SNIPPET_CHARS],
                "relevance_score": float(score) if score is not None else None,
            }
        )

    return sources


def build_answer_chain():
    """
    Builds the generation chain that takes a prepared `context` and `question`.

    Returns:
        A runnable mapping {"context", "question"} to the answer text.
    """

    return prompt | llm | StrOutputParser()


def sse_data(chunk: str) -> str:
    """
    Encodes a text chunk as one SSE event, with one `data:` line per text line, so
    that newlines inside the chunk survive standard SSE parsing. Empty chunks are skipped.
    """

    if not chunk:
        return ""

    return "".join(f"data: {line}\n" for line in chunk.split("\n")) + "\n"


def answer_with_sources(query: str):
    """
    Answers a query with labelled context and returns the sources used.

    Args:
        query (str): The question text.

    Returns:
        tuple[str, list[dict]]: The answer text and the sources.
    """

    docs = retrieve_documents(query)
    answer = build_answer_chain().invoke(
        {"context": format_labelled_context(docs), "question": query}
    )

    return answer, build_sources(docs)


async def process_query_with_sources(query: str = ""):
    """
    Streams an answer with labelled context, then a final `event: sources` frame.

    Yields:
        str: SSE frames. Token frames use standard multi-line `data:` encoding; the last
        frame is `event: sources` with `{"sources": [...]}` as JSON data.
    """

    docs = await run_in_threadpool(retrieve_documents, query)
    chain = build_answer_chain()

    async for chunk in chain.astream(
        {"context": format_labelled_context(docs), "question": query}
    ):
        yield sse_data(chunk)

    yield f"event: sources\ndata: {json.dumps({'sources': build_sources(docs)})}\n\n"


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
