from unittest.mock import patch
from http import HTTPStatus

def test_get_links(test_client, monkeypatch):
    """
    Test the `/urls` endpoint to ensure it returns the expected list of URLs.
    This test uses mocking to simulate database interactions and checks the
    response from the endpoint.
    Args:
        test_client: A test client instance for making HTTP requests to the application.
        monkeypatch: A pytest fixture used to dynamically modify or replace attributes.
    Mocks:
        - `app.main.check_tables_exist`: Mocked to always return `True`.
        - `app.main.get_url_embedding`: Mocked to simulate fetching documents embeddings from the database.
    Assertions:
        - The HTTP status code of the response is `HTTPStatus.OK`.
        - The JSON response matches the expected list of URLs:
          ['source/file1.txt', 'source/file2.txt'].
    """


    def mock_check_tables_exist():
        return True

    async def mock_get_urls_embedding():
        return ['source/file1.txt', 'source/file2.txt']

    monkeypatch.setattr("app.main.check_tables_exist", mock_check_tables_exist)
    monkeypatch.setattr("app.main.get_urls_embedding", mock_get_urls_embedding)

    response = test_client.get("/urls")
    print(response.json())
    assert response.status_code == HTTPStatus.OK
    assert response.json() == [
        'source/file1.txt',
        'source/file2.txt'
    ]


def test_ingest_links(test_client):
    """
    Test the ingestion of a list of URLs into the system.
    This test verifies that the `/urls` endpoint correctly processes a list of URLs
    and returns a successful response when the `ingest_url_to_pgvector` function is
    mocked.
    Args:
        test_client: A test client instance for simulating HTTP requests.
        mock_pool: A mock object for simulating a database connection pool.
    Mocks:
        app.main.ingest_url_to_pgvector: Mocked to prevent actual ingestion logic from running.
    Assertions:
        - The HTTP response status code is 200 (OK).
        - The JSON response contains the expected status and message.
    """

    urls = ["http://example.com/doc1", "http://example.com/doc2"]

    with patch("app.main.ingest_url_to_pgvector") as mock_ingest:
        mock_ingest.return_value = None

        response = test_client.post(
            "/urls",
            json=urls
        )
        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"status": HTTPStatus.OK, "message": "Data preparation succeeded"}


def test_ingest_invalid_links(test_client):
    """
    Test the ingestion of invalid URLs.
    This test verifies that the application correctly handles invalid URLs by
    raising an exception and returning an appropriate HTTP error response.
    Args:
        test_client: A test client instance for simulating HTTP requests.
        mock_pool: A mock object representing the database connection pool.
    Mocks:
        app.main.ingest_url_to_pgvector: Mocked to raise an exception when called.
    Expected Outcome:
        The application should return a 500 status code and an error message
        indicating that the URL is invalid.
    """

    urls = ["http://invalid-url.invalid"]

    with patch("app.main.ingest_url_to_pgvector") as mock_ingest:
        mock_ingest.side_effect = Exception("Invalid URL")

        response = test_client.post(
            "/urls",
            json=urls
        )
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "Invalid URL"}


def test_delete_links(test_client):
    """
    Test the `delete_links` endpoint to ensure it deletes the specified URL and its associated embeddings.
    Args:
        test_client (TestClient): A test client instance for simulating HTTP requests
    Mocks:
        app.main.check_tables_exist: Mocked to always return `True`.
        app.main.delete_embeddings_url: Mocked to simulate the deletion of embeddings for the given URL.
    Assertions:
        - Verifies that the HTTP DELETE request to the `/urls` endpoint with the specified URL
          returns a status code of HTTPStatus.NO_CONTENT (204).
    """

    def mock_check_tables_exist():
        return True

    with patch("app.main.check_tables_exist", mock_check_tables_exist):
        with patch("app.main.delete_embeddings_url") as mock_delete_embeddings:
            mock_delete_embeddings.return_value = True

            response = test_client.delete(
                "/urls",
                params={"url": "http://example.com/doc1"}
            )
            assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_all_links(test_client):
    """
    Test case for deleting all links via the DELETE /urls endpoint.
    This test verifies that the DELETE /urls endpoint correctly handles a request
    to delete all links when the "delete_all" parameter is set to True. It mocks
    the `delete_embeddings_url` function to ensure the endpoint behaves as expected
    without performing actual deletions.
    Args:
        test_client: A test client instance for simulating HTTP requests.
    Mocks:
        app.main.check_tables_exist: Mocked to always return `True`.
        app.main.delete_embeddings_url: Mocked to simulate the deletion of all URL embeddings.
    Assertions:
        - Ensures the response status code is HTTPStatus.NO_CONTENT (204).
    """


    def mock_check_tables_exist():
        return True

    with patch("app.main.check_tables_exist", mock_check_tables_exist):
        with patch("app.main.delete_embeddings_url") as mock_delete_embeddings:
            mock_delete_embeddings.return_value = True

            response = test_client.delete(
                "/urls",
                params={"delete_all": True}
            )
            assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_not_found_links(test_client):
    """
    Test case for deleting a URL that does not exist in the vector database.
    This test verifies the behavior of the DELETE endpoint when attempting to delete
    embeddings for a URL that is not present in the vector database. It mocks the
    `delete_embeddings_url` function to simulate a failure scenario and ensures that
    the API responds with the appropriate error status and message.
    Args:
        test_client: A test client instance for simulating HTTP requests to the API.
    Mocks:
        app.main.check_tables_exist: Mocked to always return `True`.
        app.main.delete_embeddings_url: Mocked to simulate the deletion of all URL embeddings.
    Assertions:
        - The response status code is HTTP 500 Internal Server Error.
        - The response JSON contains the expected error message indicating the failure
          to delete URL embeddings from the vector database.
    """

    def mock_check_tables_exist():
        return True

    with patch("app.main.check_tables_exist", mock_check_tables_exist):
        with patch("app.main.delete_embeddings_url") as mock_delete_embeddings:
            mock_delete_embeddings.return_value = False

            response = test_client.delete(
                "/urls",
                params={"url": "http://nonexistent-url.com"}
            )
            assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
            assert response.json() == {"detail": "Failed to delete URL embeddings from vector database."}