import pytest
from fastapi.testclient import TestClient
from unittest import mock
from retriever_server import app, retriever

client = TestClient(app)

# Mock the MilvusRetriever class
@pytest.fixture(autouse=True)
def mock_retriever():
    with mock.patch("retriever_server.retriever") as mock_retriever:
        yield mock_retriever


def test_health_check():
    """
    Test the health check endpoint.
    """
    response = client.get("/v1/retrieval/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_retrieval_success(mock_retriever):
    """
    Test the retrieval endpoint with valid input.
    """
    mock_retriever.search.return_value = [
        {"id": "1", "distance": 0.1, "entity": {"meta": {"key": "value1"}}},
        {"id": "2", "distance": 0.2, "entity": {"meta": {"key": "value2"}}},
    ]

    request_data = {
        "query": "example query",
        "filter": {"type": "example"},
        "max_num_results": 2
    }

    response = client.post("/v1/retrieval", json=request_data)
    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"id": "1", "distance": 0.1, "meta": {"key": "value1"}},
            {"id": "2", "distance": 0.2, "meta": {"key": "value2"}}
        ]
    }


def test_retrieval_empty_results(mock_retriever):
    """
    Test the retrieval endpoint when no results are found.
    """
    mock_retriever.search.return_value = []

    request_data = {
        "query": "example query",
        "filter": {"type": "example"},
        "max_num_results": 2
    }

    response = client.post("/v1/retrieval", json=request_data)
    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_retrieval_error(mock_retriever):
    """
    Test the retrieval endpoint when an error occurs.
    """
    mock_retriever.search.side_effect = Exception("Mocked retrieval error")

    request_data = {
        "query": "example query",
        "filter": {"type": "example"},
        "max_num_results": 2
    }

    response = client.post("/v1/retrieval", json=request_data)
    assert response.status_code == 500
    assert response.json() == {"detail": "Error during retrieval: Mocked retrieval error"}