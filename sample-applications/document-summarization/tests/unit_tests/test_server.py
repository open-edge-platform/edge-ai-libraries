import io
import pytest
from fastapi.testclient import TestClient
from app.server import app, is_file_supported, ensure_directory_exists, clean_directory


client = TestClient(app)

def test_version_endpoint():
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": "1.0"}

def test_is_file_supported():
    assert is_file_supported("test.pdf")
    assert is_file_supported("test.docx")
    assert is_file_supported("test.txt")
    assert not is_file_supported("test.exe")
    assert not is_file_supported("test")

def test_ensure_and_clean_directory(tmp_path):
    test_dir = tmp_path / "docs"
    ensure_directory_exists(str(test_dir))
    assert test_dir.exists()
    # Create a file
    file_path = test_dir / "file.txt"
    file_path.write_text("content")
    assert file_path.exists()
    # Clean directory
    clean_directory(str(test_dir))
    assert not any(test_dir.iterdir())

def test_summarize_unsupported_file():
    file_content = b"dummy"
    response = client.post(
        "/summarize/",
        files={"file": ("test.exe", io.BytesIO(file_content), "application/octet-stream")},
        data={"query": "Summarize the document"},
    )
    assert response.status_code == 400
    assert "Only" in response.json()["message"]

def test_summarize_missing_file():
    response = client.post("/summarize/", data={"query": "Summarize the document"})
    assert response.status_code == 422  # Unprocessable Entity (missing required file)

def test_summarize_supported_file(mocker):
    # Mock the summarization logic to avoid actual model inference
    mock_summary = "This is a summary."
    mocker.patch(
    "app.server.SimpleSummaryPack",
    autospec=True,
    return_value=mocker.Mock(run=lambda filename: iter(mock_summary)))

    file_content = b"Sample document content."
    response = client.post(
        "/summarize/",
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        data={"query": "Summarize the document"},
    )
    assert response.status_code == 200
    assert mock_summary in response.text or mock_summary in response.json().get("summary", "")