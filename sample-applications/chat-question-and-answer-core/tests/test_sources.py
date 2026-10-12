import json
import queue
import time

import numpy as np
import pytest
from langchain_core.documents import Document


class FakeRetriever:
    def __init__(self, docs):
        self.docs = docs

    def invoke(self, query):
        return list(self.docs)


class FakeVectorStore:
    def __init__(self, docs):
        self.docs = docs
        self.kwargs = None

    def as_retriever(self, **kwargs):
        self.kwargs = kwargs
        return FakeRetriever(self.docs)


class FakeReranker:
    """Mimics OpenVINOReranker.compress_documents: keeps only `id` and `relevance_score`."""

    def compress_documents(self, documents, query):
        order = [1, 0]
        return [
            Document(
                page_content=documents[i].page_content,
                metadata={"id": i, "relevance_score": np.float32(0.9 - 0.4 * n)},
            )
            for n, i in enumerate(order)
        ]


class FakeAnswerChain:
    def __init__(self, chunks):
        self.chunks = chunks
        self.inputs = []

    def invoke(self, inputs):
        self.inputs.append(inputs)
        return "".join(self.chunks)

    async def astream(self, inputs):
        self.inputs.append(inputs)
        for chunk in self.chunks:
            yield chunk


class FakeStreamer:
    """Stands in for transformers.TextIteratorStreamer."""

    def __init__(self, tokenizer, **kwargs):
        self.queue = queue.Queue()

    def put_text(self, text):
        self.queue.put(text)

    def end(self):
        self.queue.put(None)

    def __iter__(self):
        return self

    def __next__(self):
        text = self.queue.get()
        if text is None:
            raise StopIteration
        return text


class FakePipeline:
    """Stands in for the HF text-generation pipeline of the OpenVINO LLM."""

    tokenizer = None

    def __init__(self, tokens=None, generated_text=""):
        self.tokens = tokens
        self.generated_text = generated_text
        self.prompts = []
        self.produced = 0

    def __call__(self, prompt, streamer=None, stopping_criteria=None, **kwargs):
        self.prompts.append(prompt)
        if streamer is not None:
            tokens = self.tokens if self.tokens is not None else (f"t{i} " for i in range(1000))
            for token in tokens:
                if stopping_criteria and any(c(None, None) for c in stopping_criteria):
                    break
                streamer.put_text(token)
                self.produced += 1
                time.sleep(0.001)
        return [{"generated_text": self.generated_text}]


class FakePipelineLLM:
    def __init__(self, pipeline):
        self.pipeline = pipeline


CANDIDATES = [
    Document(page_content="Torque the bolts to 25 Nm.", metadata={"source": "/tmp/chatqna/documents/manual.pdf", "page": 4, "page_label": "5"}),
    Document(page_content="Disconnect the battery first.", metadata={"source": "/tmp/chatqna/documents/manual.pdf", "page": 9}),
]


@pytest.fixture
def chain():
    # Imported lazily: app.config needs the dummy model config created by conftest.py.
    from app import chain as chain_module
    return chain_module


@pytest.fixture
def config():
    from app.config import config as settings
    return settings


@pytest.fixture(autouse=True)
def rerank_enabled(mocker, config):
    # The ollama runtime disables reranking; these tests use FakeReranker on both runtimes.
    mocker.patch.object(config, "_ENABLE_RERANK", True)


@pytest.fixture
def sources_enabled(mocker, config):
    mocker.patch.object(config, "RETURN_SOURCES", True)
    yield


@pytest.fixture
def chain_llm(mocker, chain):
    # An LLM without `pipeline` (e.g. Ollama) streams through build_answer_chain().
    mocker.patch.object(chain, "llm", object(), create=True)


@pytest.fixture
def pipeline_streamer(mocker):
    pytest.importorskip("transformers")
    mocker.patch("transformers.TextIteratorStreamer", FakeStreamer)


def parse_sse(text):
    """Minimal SSE parser following the WHATWG event-stream rules used by browsers."""
    events, data, event = [], [], "message"
    for line in text.split("\n"):
        if line == "":
            if data:
                events.append((event, "\n".join(data)))
            data, event = [], "message"
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
        elif field == "event":
            event = value
    return events


def test_retrieve_documents_restores_metadata_after_rerank(mocker, chain):
    mocker.patch.object(chain, "vectorstore", FakeVectorStore(CANDIDATES))
    mocker.patch.object(chain, "reranker", FakeReranker(), create=True)

    docs = chain.retrieve_documents("How do I torque the bolts?")

    assert [d.page_content for d in docs] == [CANDIDATES[1].page_content, CANDIDATES[0].page_content]
    assert docs[0].metadata["source"].endswith("manual.pdf")
    assert docs[0].metadata["page"] == 9
    assert docs[1].metadata["page_label"] == "5"
    assert isinstance(docs[0].metadata["relevance_score"], float)
    assert docs[0].metadata["relevance_score"] == pytest.approx(0.9)


def test_retrieve_documents_without_vectorstore(mocker, chain):
    mocker.patch.object(chain, "vectorstore", None)
    assert chain.retrieve_documents("anything") == []


def test_labelled_context_and_sources(chain):
    context = chain.format_labelled_context(CANDIDATES)
    assert context.startswith("[S1] manual.pdf, page 5\nTorque the bolts")
    assert "[S2] manual.pdf, page 10\nDisconnect the battery" in context

    sources = chain.build_sources(CANDIDATES)
    assert sources[0] == {
        "id": "S1",
        "source": "manual.pdf",
        "page": 4,
        "page_label": "5",
        "snippet": "Torque the bolts to 25 Nm.",
        "relevance_score": None,
    }
    assert sources[1]["id"] == "S2"
    assert sources[1]["page_label"] == "10"


def test_sse_data_keeps_newlines_and_leading_spaces(chain):
    for chunk in ["\n", " the", "1. Remove\n2. Install", ""]:
        events = parse_sse(chain.sse_data(chunk))
        assert events == ([("message", chunk)] if chunk else [])


def test_chat_json_unchanged_when_flag_off(test_client, mocker, config):
    mocker.patch.object(config, "RETURN_SOURCES", False)
    fake_chain = mocker.Mock()
    fake_chain.invoke.return_value = "stock answer"
    mocker.patch("app.server.get_retriever", return_value=None)
    mocker.patch("app.server.build_chain", return_value=fake_chain)

    response = test_client.post("/chat", json={"input": "What is AI?", "stream": False})

    assert response.status_code == 200
    assert response.json() == {"status": "Success", "metadata": "stock answer"}


def test_chat_json_with_sources(test_client, mocker, sources_enabled, chain):
    mocker.patch.object(chain, "vectorstore", FakeVectorStore(CANDIDATES))
    mocker.patch.object(chain, "reranker", FakeReranker(), create=True)
    fake_chain = FakeAnswerChain(["1. Disconnect the battery [S1]."])
    mocker.patch.object(chain, "build_answer_chain", return_value=fake_chain)

    response = test_client.post("/chat", json={"input": "How?", "stream": False})

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"] == "1. Disconnect the battery [S1]."
    assert [s["id"] for s in body["sources"]] == ["S1", "S2"]
    assert body["sources"][0]["page"] == 9
    assert body["sources"][0]["relevance_score"] == pytest.approx(0.9)
    assert fake_chain.inputs[0]["context"].startswith("[S1] manual.pdf, page 10")
    assert fake_chain.inputs[0]["question"] == "How?"


def test_chat_stream_with_sources_event(test_client, mocker, sources_enabled, chain, chain_llm):
    mocker.patch.object(chain, "vectorstore", FakeVectorStore(CANDIDATES))
    mocker.patch.object(chain, "reranker", FakeReranker(), create=True)
    mocker.patch.object(chain, "build_answer_chain", return_value=FakeAnswerChain(["1. Disconnect", "\n", "2. Torque [S2]"]))

    response = test_client.post("/chat", json={"input": "How?", "stream": True})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    events = parse_sse(response.text)
    tokens = "".join(data for event, data in events if event == "message")
    assert tokens == "1. Disconnect\n2. Torque [S2]"
    assert events[0][0] == "sources"
    sources = json.loads(events[0][1])["sources"]
    assert [s["id"] for s in sources] == ["S1", "S2"]
    assert sources[1]["page_label"] == "5"


def test_chat_stream_with_sources_and_empty_store(test_client, mocker, sources_enabled, chain, chain_llm):
    mocker.patch.object(chain, "vectorstore", None)
    mocker.patch.object(chain, "build_answer_chain", return_value=FakeAnswerChain(["No context."]))

    response = test_client.post("/chat", json={"input": "How?", "stream": True})

    events = parse_sse(response.text)
    assert events[0] == ("sources", json.dumps({"sources": []}))


def test_retrieval_depth_from_config(mocker, chain, config):
    store = FakeVectorStore(CANDIDATES)
    reranker = FakeReranker()
    mocker.patch.object(chain, "vectorstore", store)
    mocker.patch.object(chain, "reranker", reranker, create=True)
    mocker.patch.object(config, "RETRIEVAL_K", 8)
    mocker.patch.object(config, "RERANK_TOP_N", 4)

    chain.retrieve_documents("How?")

    assert store.kwargs["search_kwargs"]["k"] == 8
    assert store.kwargs["search_kwargs"]["fetch_k"] >= 16
    assert reranker.top_n == 4


def test_retrieval_query_unchanged_without_prompt(mocker, chain, config):
    pipeline = FakePipeline(generated_text="rewritten")
    mocker.patch.object(chain, "llm", FakePipelineLLM(pipeline), create=True)
    mocker.patch.object(config, "RETRIEVAL_TRANSLATE_PROMPT", "")

    assert chain.retrieval_query("Jak dokręcić śruby?") == "Jak dokręcić śruby?"
    assert pipeline.prompts == []


def test_retrieval_query_rewrites_with_prompt(mocker, chain, config):
    pipeline = FakePipeline(generated_text="\n  How do I torque the bolts?\nExtra line")
    mocker.patch.object(chain, "llm", FakePipelineLLM(pipeline), create=True)
    mocker.patch.object(config, "RETRIEVAL_TRANSLATE_PROMPT", "Translate to English: {question}")

    assert chain.retrieval_query("Jak dokręcić śruby?") == "How do I torque the bolts?"
    assert pipeline.prompts == ["Translate to English: Jak dokręcić śruby?"]


def test_retrieval_query_without_pipeline(mocker, chain, config, chain_llm):
    mocker.patch.object(config, "RETRIEVAL_TRANSLATE_PROMPT", "Translate: {question}")

    assert chain.retrieval_query("Pytanie") == "Pytanie"


def test_chat_stream_with_pipeline_sends_sources_first(test_client, mocker, sources_enabled, chain, pipeline_streamer):
    from langchain_core.prompts import ChatPromptTemplate

    pipeline = FakePipeline(tokens=["1. Disconnect", "\n", "2. Torque [S2]"])
    mocker.patch.object(chain, "llm", FakePipelineLLM(pipeline), create=True)
    mocker.patch.object(chain, "prompt", ChatPromptTemplate.from_template("{context}\nQ: {question}"), create=True)
    mocker.patch.object(chain, "vectorstore", FakeVectorStore(CANDIDATES))
    mocker.patch.object(chain, "reranker", FakeReranker(), create=True)

    response = test_client.post("/chat", json={"input": "How?", "stream": True})

    events = parse_sse(response.text)
    assert events[0][0] == "sources"
    assert [s["id"] for s in json.loads(events[0][1])["sources"]] == ["S1", "S2"]
    assert "".join(data for event, data in events[1:]) == "1. Disconnect\n2. Torque [S2]"
    assert pipeline.prompts[0].startswith("Human: [S1] manual.pdf, page 10\nDisconnect the battery")
    assert pipeline.prompts[0].endswith("Q: How?")


async def test_stream_answer_stops_when_consumer_goes_away(mocker, chain, pipeline_streamer):
    pipeline = FakePipeline()
    mocker.patch.object(chain, "llm", FakePipelineLLM(pipeline), create=True)

    stream = chain.stream_answer("prompt")
    assert (await stream.__anext__()) == "t0 "
    await stream.aclose()

    # The worker releases the generation lock once the stopping criterion fires.
    assert chain._generation_lock.acquire(timeout=5)
    chain._generation_lock.release()
    assert pipeline.produced < 1000
