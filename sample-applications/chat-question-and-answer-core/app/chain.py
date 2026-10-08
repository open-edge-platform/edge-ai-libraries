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
import threading
import pandas as pd

vectorstore = None
# Set from init_models() below; stays None when RUN_TEST bypasses model loading.
llm = None

# One OpenVINO infer request serves the LLM: generations must not overlap.
_generation_lock = threading.Lock()

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
        search_kwargs={
            "k": config.RETRIEVAL_K,
            "fetch_k": max(config._FETCH_K, 2 * config.RETRIEVAL_K),
        },
        search_type=config._SEARCH_METHOD,
    )
    candidates = base_retriever.invoke(query)

    if not config._ENABLE_RERANK or not candidates:
        return list(candidates)

    reranker.top_n = config.RERANK_TOP_N
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


def _is_genai() -> bool:
    # GenAILLM (LLM on NPU) streams through a callback instead of an HF pipeline.
    return hasattr(llm, "stream_text")


def _render_prompt(docs, query: str) -> str:
    # Same text as `prompt | llm` sends (ChatPromptValue.to_string()).
    return prompt.invoke({"context": format_labelled_context(docs), "question": query}).to_string()


def fit_documents(docs, query: str):
    """
    Drops the lowest-ranked context documents until the rendered prompt fits the LLM
    prompt limit (`max_prompt_tokens`, set for the LLM on NPU). Without a limit the
    documents are returned unchanged.
    """

    limit = getattr(llm, "max_prompt_tokens", None)
    if not isinstance(limit, int) or limit <= 0:
        return docs

    docs = list(docs)
    while docs and llm.count_tokens(_render_prompt(docs, query)) > limit:
        logger.warning(f"Prompt exceeds {limit} tokens; dropping context chunk {len(docs)}.")
        docs.pop()

    return docs


def retrieval_query(query: str) -> str:
    """
    Returns the text used for retrieval. With RETRIEVAL_TRANSLATE_PROMPT set (a template
    with a `{question}` placeholder), the LLM first rewrites the question, for example
    into English for an English-only embedding model; the answer still uses `query`.
    """

    template = config.RETRIEVAL_TRANSLATE_PROMPT
    if not template or not (hasattr(llm, "pipeline") or _is_genai()):
        return query

    with _generation_lock:
        if _is_genai():
            generated = llm.generate_text(template.replace("{question}", query), max_new_tokens=64)
        else:
            out = llm.pipeline(
                template.replace("{question}", query),
                max_new_tokens=64,
                do_sample=False,
                return_full_text=False,
            )
            generated = out[0]["generated_text"]
    lines = [line.strip() for line in str(generated).splitlines() if line.strip()]

    return lines[0] if lines else query


def answer_with_sources(query: str):
    """
    Answers a query with labelled context and returns the sources used.

    Args:
        query (str): The question text.

    Returns:
        tuple[str, list[dict]]: The answer text and the sources.
    """

    docs = fit_documents(retrieve_documents(retrieval_query(query)), query)
    with _generation_lock:
        answer = build_answer_chain().invoke(
            {"context": format_labelled_context(docs), "question": query}
        )

    return answer, build_sources(docs)


def _generate(prompt_text: str, streamer, cancel: threading.Event, errors: list) -> None:
    from transformers import StoppingCriteria, StoppingCriteriaList

    class Cancelled(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):
            return cancel.is_set()

    try:
        with _generation_lock:
            if cancel.is_set():
                pass
            elif _is_genai():
                llm.stream_text(
                    prompt_text, on_text=streamer.put, cancel=cancel, max_new_tokens=config.MAX_TOKENS
                )
            else:
                llm.pipeline(
                    prompt_text,
                    streamer=streamer,
                    stopping_criteria=StoppingCriteriaList([Cancelled()]),
                    max_new_tokens=config.MAX_TOKENS,
                    return_full_text=False,
                )
    except Exception as exc:
        errors.append(exc)
    finally:
        # Unblocks the consumer also when generation failed or never started.
        streamer.end()


async def stream_answer(prompt_text: str):
    """
    Streams LLM text for a rendered prompt. Generation stops at the next token when the
    consumer goes away (client disconnect), so the next request does not find the
    infer request busy.
    """

    if _is_genai():
        from .openvino_xpu import TextQueue

        streamer = TextQueue()
    else:
        from transformers import TextIteratorStreamer

        streamer = TextIteratorStreamer(
            llm.pipeline.tokenizer, timeout=None, skip_prompt=True, skip_special_tokens=True
        )
    cancel = threading.Event()
    errors: list = []
    threading.Thread(
        target=_generate, args=(prompt_text, streamer, cancel, errors), daemon=True
    ).start()
    try:
        while True:
            chunk = await run_in_threadpool(next, streamer, None)
            if chunk is None:
                break
            yield chunk
    finally:
        cancel.set()

    if errors:
        raise errors[0]


async def process_query_with_sources(query: str = ""):
    """
    Streams an `event: sources` frame first, then the answer with labelled context.

    Yields:
        str: SSE frames. The first frame is `event: sources` with `{"sources": [...]}`
        as JSON data; token frames use standard multi-line `data:` encoding.
    """

    docs = await run_in_threadpool(retrieve_documents, await run_in_threadpool(retrieval_query, query))
    docs = await run_in_threadpool(fit_documents, docs, query)
    yield f"event: sources\ndata: {json.dumps({'sources': build_sources(docs)})}\n\n"

    inputs = {"context": format_labelled_context(docs), "question": query}
    if hasattr(llm, "pipeline") or _is_genai():
        # Same text as `prompt | llm` sends (ChatPromptValue.to_string()).
        chunks = stream_answer(prompt.invoke(inputs).to_string())
    else:
        chunks = build_answer_chain().astream(inputs)

    async for chunk in chunks:
        yield sse_data(chunk)


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
