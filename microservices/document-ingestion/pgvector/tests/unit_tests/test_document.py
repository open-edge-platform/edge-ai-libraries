from unittest.mock import patch, AsyncMock
from http import HTTPStatus
from app.store import DataStore
import pytest

def test_get_documents(test_client, monkeypatch):
    """
    Test the `GET /documents` endpoint.
    This test verifies that the endpoint correctly retrieves a list of documents
    from the database and returns them in the expected JSON format.
    Args:
        test_client: A test client instance for simulating HTTP requests.
        monkeypatch: A pytest fixture for dynamically modifying or replacing attributes.
    Mocks:
        - `app.main.check_tables_exist`: Mocked to always return `True`, simulating that the required tables exist.
        - `app.main.get_document_embedding`: Mocked to simulate fetching documents embeddings from the database.
    Assertions:
        - The HTTP status code of the response is `HTTPStatus.OK`.
        - The JSON response matches the expected list of documents with their file names and bucket names.
    """

    def mock_check_tables_exist():
        return True

    async def mock_get_document_embedding():
        return [
            {"file_name": "file1.txt", "bucket_name": "bucket1"},
            {"file_name": "file2.txt", "bucket_name": "bucket2"}
        ]

    monkeypatch.setattr("app.main.check_tables_exist", mock_check_tables_exist)
    monkeypatch.setattr("app.main.get_documents_embeddings", mock_get_document_embedding)

    response = test_client.get("/documents")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == [
        {"file_name": "file1.txt", "bucket_name": "bucket1"},
        {"file_name": "file2.txt", "bucket_name": "bucket2"}
    ]


def test_ingest_documents(test_client, test_file):
    """
    Test the `ingest_document` endpoint.
    This test verifies the behavior of the document ingestion process, including:
    1. Mocking the external `requests.post` call to simulate file upload and bucket response.
    2. Mocking the `ingest_to_pgvector` function to ensure it is called without executing its logic.
    3. Sending a POST request to the `/documents` endpoint with a sample file and validating the response.
    Args:
        test_client: A test client instance for simulating HTTP requests.
        test_file: A dictionary containing the file path of the test file to be uploaded.
    Mocks:
        - `app.main.DataStore.upload_document`: Simulates the file upload process to the storage bucket.
        - `app.main.ingest_to_pgvector`: Simulates the ingestion process to the pgvector database.
    Assertions:
        - Ensures the response status code is HTTP 200 (OK).
        - Validates the response JSON structure and content.
    """

    mock_upload_result = {
        "bucket": "test_bucket",
        "file": "sample-file.txt",
    }

    with patch("app.main.DataStore.upload_document", return_value=mock_upload_result):
        result = DataStore.upload_document("sample-file.txt")
        bucket_name = result["bucket"]
        uploaded_file_name = result["file"]

        assert bucket_name == "test_bucket"
        assert uploaded_file_name == "sample-file.txt"

        with patch("app.main.ingest_to_pgvector") as mock_ingest:
            mock_ingest.return_value = None

            response = test_client.post(
                "/documents",
                files={"files": ("sample-file.txt", open(test_file["file_path"], "rb"), "text/plain")}
            )
            assert response.status_code == HTTPStatus.OK
            assert response.json() == {"status": HTTPStatus.OK, "message": "Data preparation succeeded"}


def test_ingest_unsupported_document(test_client, test_file):
    """
    Test case for verifying the behavior of the document ingestion endpoint
    when an unsupported file format is uploaded.
    Args:
        test_client: A test client instance for simulating HTTP requests.
        test_file: A dictionary containing the file path of the test file.
    Assertions:
        - Ensures that the HTTP response status code is 400 (Bad Request).
        - Validates that the response JSON contains an appropriate error message
          indicating the unsupported file format and listing the supported formats.
    """

    response = test_client.post(
        "/documents",
        files={"files": ("sample-file.pptx", open(test_file["file_path"], "rb"), "application/octet-stream")}
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        "detail": 'Unsupported file format: .pptx. Supported formats are: pdf, txt, docx'
    }


def test_delete_documents(test_client):
    """
    Test the deletion of documents via the DELETE endpoint.
    This test verifies that the DELETE request to the `/documents` endpoint
    successfully deletes a document when provided with the correct parameters.
    It mocks the external dependencies, including the `requests.delete` call
    and the `delete_embeddings` function, to ensure the test is isolated from
    external systems.
    Args:
        test_client: A test client instance for simulating HTTP requests.
    Mocks:
        - `app.main.check_tables_exist`: Mocked to always return `True`, simulating that the required tables exist.
        - `app.main.delete_embeddings`: Simulates the deletion of embeddings associate with the document.
        - `app.main.DataStore.delete_document`: Mocked to simulate the deletion of the document from the storage.
    Assertions:
        - Ensures the DELETE request returns a status code of HTTP 204 (NO CONTENT).
    """

    def mock_check_tables_exist():
        return True

    with patch("app.main.check_tables_exist", mock_check_tables_exist):
        with patch("app.main.delete_embeddings") as mock_delete_embeddings:
            mock_delete_embeddings.return_value = True

            with patch("app.main.DataStore.delete_document") as mock_delete:
                mock_delete.return_value.status_code = HTTPStatus.NO_CONTENT

                response = test_client.delete(
                    "/documents",
                    params={"bucket_name": "test_bucket", "file_name": "sample-file.txt"}
                )
                assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_all_documents(test_client):
    """
    Test case for deleting all documents from a specified bucket.
    This test verifies that the DELETE request to the "/documents" endpoint
    with the appropriate parameters successfully deletes all documents and
    returns the expected HTTP status code.
    Args:
        test_client: A test client instance used to simulate HTTP requests.
    Mocks:
        - `app.main.check_tables_exist`: Mocked to always return `True`, simulating that the required tables exist.
        - `app.main.delete_embeddings`: Simulates the deletion of embeddings to ensure the operation completes successfully.
        - `app.main.DataStore.delete_document`: Mocked to simulate the deletion of all documents from the storage.
    Assertions:
        - Ensures the response status code is HTTPStatus.NO_CONTENT (204).
    """

    def mock_check_tables_exist():
        return True

    with patch("app.main.check_tables_exist", mock_check_tables_exist):
        with patch("app.main.delete_embeddings") as mock_delete_embeddings:
            mock_delete_embeddings.return_value = True

            with patch("app.main.DataStore.delete_document") as mock_delete:
                mock_delete.return_value.status_code = HTTPStatus.NO_CONTENT

                response = test_client.delete(
                    "/documents",
                    params={"bucket_name": "test_bucket", "delete_all": True}
                )
                assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_documents_not_found(test_client):
    """
    Test case for deleting documents when the specified file is not found.
    This test simulates a scenario where a DELETE request is made to remove a document
    that does not exist in the storage. It mocks the external dependencies to ensure
    the behavior of the application is tested in isolation.
    Args:
        test_client: A test client instance for simulating HTTP requests to the application.
    Mocks:
        - `app.main.check_tables_exist`: Mocked to always return `True`, simulating that the required tables exist.
        - `app.main.delete_embeddings`: Mocked to simulate the deletion of embeddings from the vector database.
        - `app.main.DataStore.delete_document`: Mocked to simulate the deletion of a document from the storage.
    Assertions:
        - Verifies that the HTTP response status code is 500 (Internal Server Error).
        - Verifies that the response JSON contains the appropriate error message.
    """

    def mock_check_tables_exist():
        return True

    with patch("app.main.check_tables_exist", mock_check_tables_exist):
        with patch("app.main.delete_embeddings") as mock_delete_embeddings:
            mock_delete_embeddings.return_value = False

            with patch("app.main.DataStore.delete_document") as mock_delete:
                mock_delete.return_value.status_code = HTTPStatus.INTERNAL_SERVER_ERROR

                response = test_client.delete(
                    "/documents",
                    params={"bucket_name": "test_bucket", "file_name": "nonexistent-file.txt"}
                )
                assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
                assert response.json() == {"detail": "Failed to delete embeddings from vector database."}


@pytest.mark.asyncio
async def test_download_documents(test_client):
    """
    Test the functionality of downloading documents from the API.
    This test mocks the `get_document_size` and `download_document` methods
    of the `DataStore` class to simulate the behavior of the document
    download endpoint. It verifies that the response contains the correct
    status code, headers, and content.
    Args:
        test_client (TestClient): The test client used to make requests to the API.
    Raises:
        AssertionError: If the response does not meet the expected conditions.
    """

    def mock_get_document_size():
        return 1024

    with patch("app.main.DataStore.get_document_size", mock_get_document_size):
        with patch("app.main.DataStore.download_document", new_callable=AsyncMock) as mock_download:
            return mock_download

        response = await test_client.get("/documents/testfile.txt?bucket_name=test_bucket")

        assert response.status_code == HTTPStatus.OK
        assert response.headers["Content-Length"] == "1024"
        assert response.headers["Content-Disposition"] == "attachment; filename=testfile.txt"

@pytest.mark.asyncio
async def test_download_invalid_documents(test_client):
    """
    Test the behavior of the document download endpoint when attempting to
    download a non-existent document.
    This test mocks the `get_document_size` method to raise a `FileNotFoundError`
    and verifies that the API responds with a 404 status code and the appropriate
    error message.
    Args:
        test_client (TestClient): The test client used to simulate HTTP requests.
    Raises:
        FileNotFoundError: Simulated exception for a missing file.
    Asserts:
        - The HTTP response status code is 404 (NOT FOUND).
        - The response JSON contains the expected error message.
    """

    def mock_get_document_size():
        raise FileNotFoundError("File not found")

    with patch("app.main.DataStore.get_document_size", mock_get_document_size):
        with patch("app.main.DataStore.download_document", new_callable=AsyncMock) as mock_download:
            return mock_download

        response = await test_client.get("/documents/testfile.txt?bucket_name=testbucket")

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert response.json() == {"detail": "File not found"}