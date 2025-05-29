import os
import pytest
from fastapi.testclient import TestClient
from unittest import mock
from dataprep_visual import app, indexer
from fastapi import HTTPException

DEVICE = os.getenv("DEVICE", "CPU")


client = TestClient(app)

# Mock the Indexer class
@pytest.fixture(autouse=True)
def mock_indexer():
    with mock.patch("dataprep_visual.indexer") as mock_indexer:
        yield mock_indexer


def test_health_check():
    """
    Test the health check endpoint.
    """
    response = client.get("/v1/dataprep/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_info_endpoint(mock_indexer):
    """
    Test the info endpoint.
    """
    mock_indexer.model_id = "mock_model_id"
    mock_indexer.model_path = "/mock/path/to/model"
    mock_indexer.count_files.return_value = 10

    response = client.get("/v1/dataprep/info")
    assert response.status_code == 200
    assert response.json() == {
        "model_id": "mock_model_id",
        "model_path": "/mock/path/to/model",
        "device": DEVICE,
        "Number of processed files": 10,
    }


def test_ingest_host_dir(mock_indexer):
    """
    Test the ingest endpoint.
    """
    mock_indexer.add_embedding.return_value = "mock_db_response"

    request_data = {
        "file_dir": "/mock/host/dir",
        "frame_extract_interval": 15,
        "do_detect_and_crop": True,
    }

    with mock.patch("os.path.isdir", return_value=True):
        response = client.post("/v1/dataprep/ingest", json=request_data)

    assert response.status_code == 200
    assert response.json() == {
        "message": "Files successfully processed. db returns mock_db_response"
    }

def test_ingest_host_dir_notexist(mock_indexer):
    """
    Test the ingest endpoint.
    """
    mock_indexer.add_embedding.return_value = "mock_db_response"

    request_data = {
        "file_dir": "/mock/host/dir",
        "frame_extract_interval": 15,
        "do_detect_and_crop": True,
    }

    response = client.post("/v1/dataprep/ingest", json=request_data)

    assert response.status_code == 500
    assert "Error" in response.json()["detail"]


def test_ingest_host_file(mock_indexer):
    """
    Test the ingest endpoint.
    """
    mock_indexer.add_embedding.return_value = "mock_db_response"

    request_data = {
        "file_path": "/mock/host/file.mp4",
        "meta": {"key": "value"},
        "frame_extract_interval": 15,
        "do_detect_and_crop": True,
    }

    with mock.patch("os.path.exists", return_value=True):
        response = client.post("/v1/dataprep/ingest", json=request_data)

    assert response.status_code == 200
    assert response.json() == {
        "message": "Files successfully processed. db returns mock_db_response"
    }

def test_ingest_host_file_notexist(mock_indexer):
    """
    Test the ingest endpoint.
    """
    mock_indexer.add_embedding.return_value = "mock_db_response"

    request_data = {
        "file_dir": "/mock/host/dir",
        "frame_extract_interval": 15,
        "do_detect_and_crop": True,
    }

    response = client.post("/v1/dataprep/ingest", json=request_data)

    assert response.status_code == 500
    assert "Error" in response.json()["detail"]


def test_get_file_info(mock_indexer):
    """
    Test the get_file_info endpoint.
    """
    mock_indexer.query_file.return_value = ("mock_result", ["id1", "id2"])

    with mock.patch("os.path.exists", return_value=True):
        response = client.get("/v1/dataprep/get", params={"file_path": "/mock/file/path"})

    assert response.status_code == 200
    assert response.json() == {
        "file_path": "/mock/file/path",
        "ids_in_db": ["id1", "id2"],
    }


def test_delete_file_in_db(mock_indexer):
    """
    Test the delete_file_in_db endpoint.
    """
    mock_indexer.delete_by_file_path.return_value = ("mock_result", ["id1", "id2"])

    with mock.patch("os.path.exists", return_value=True):
        response = client.delete("/v1/dataprep/delete", params={"file_path": "/mock/file/path"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "File successfully deleted. db returns: mock_result",
        "removed_ids": ["id1", "id2"],
    }


def test_clear_db(mock_indexer):
    """
    Test the clear_db endpoint.
    """
    mock_indexer.delete_all.return_value = ("mock_result", None)

    response = client.delete("/v1/dataprep/delete_all")
    assert response.status_code == 200
    assert response.json() == {
        "message": "Database successfully cleared. db returns: mock_result"
    }