import json

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


@pytest.fixture
def sources_enabled(mocker, config):
    mocker.patch.object(config, "RETURN_SOURCES", True)
    yield


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


def test_chat_stream_with_sources_event(test_client, mocker, sources_enabled, chain):
    mocker.patch.object(chain, "vectorstore", FakeVectorStore(CANDIDATES))
    mocker.patch.object(chain, "reranker", FakeReranker(), create=True)
    mocker.patch.object(chain, "build_answer_chain", return_value=FakeAnswerChain(["1. Disconnect", "\n", "2. Torque [S2]"]))

    response = test_client.post("/chat", json={"input": "How?", "stream": True})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    events = parse_sse(response.text)
    tokens = "".join(data for event, data in events if event == "message")
    assert tokens == "1. Disconnect\n2. Torque [S2]"
    assert events[-1][0] == "sources"
    sources = json.loads(events[-1][1])["sources"]
    assert [s["id"] for s in sources] == ["S1", "S2"]
    assert sources[1]["page_label"] == "5"


def test_chat_stream_with_sources_and_empty_store(test_client, mocker, sources_enabled, chain):
    mocker.patch.object(chain, "vectorstore", None)
    mocker.patch.object(chain, "build_answer_chain", return_value=FakeAnswerChain(["No context."]))

    response = test_client.post("/chat", json={"input": "How?", "stream": True})

    events = parse_sse(response.text)
    assert events[-1] == ("sources", json.dumps({"sources": []}))
