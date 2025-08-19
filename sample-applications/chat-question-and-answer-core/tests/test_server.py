import tempfile
from http import HTTPStatus


def test_chain_response(test_client, mocker):
    """
    Tests the chain response functionality of the server by simulating a POST
    request to the `/chat` endpoint and verifying the streamed response.
    Args:
        test_client: A test client instance used to simulate HTTP requests.
        mocker: A mocking library instance used to patch dependencies.
    Mocks:
        - `app.server.get_retriever`: Mocked to return `True`.
        - `app.server.build_chain`: Mocked to return `True`.
        - `app.server.process_query`: Mocked to return an iterator with values `["one", "two"]`.
    Raises:
        AssertionError: If any of the assertions fail.
    """

    payload = {"input": "What is AI?", "stream": True}

    mocker.patch("app.server.get_retriever", return_value=True)
    mocker.patch("app.server.build_chain", return_value=True)
    mocker.patch("app.server.process_query", return_value=iter(["one", "two"]))

    response = test_client.post("/chat", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    streamed_data = ""
    for chunk in response.iter_text():
        streamed_data += chunk

    assert "one" in streamed_data
    assert "two" in streamed_data


def test_success_upload_and_create_embedding(test_client, mocker):
    """
    Tests the successful upload of a document and the creation of embeddings.
    This test simulates the process of uploading a text file, validating the document,
    saving it, and creating embeddings using a mocked FAISS vector database. It verifies
    that the API endpoint responds with the correct status code and response JSON.
    Args:
        test_client: A test client instance used to simulate HTTP requests to the API.
        mocker: A mocking library instance used to patch functions and simulate behavior.
    Mocks:
        - `app.server.validate_document`: Mocked to return `True`.
        - `app.server.save_document`: Mocked to return the temporary file name and `None`.
        - `app.server.create_faiss_vectordb`: Mocked to return `True`.
    Assertions:
        - The response status code is 200.
        - The response JSON matches the expected success message and metadata.
    """

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
        tmp_file.write(b"This is sample txt file.")
        tmp_file.seek(0)

        mocker.patch("app.server.validate_document", return_value=True)
        mocker.patch("app.server.save_document", return_value=(tmp_file.name, None))
        mocker.patch("app.server.create_faiss_vectordb", return_value=True)


        response = test_client.post("/documents", files={"files": (tmp_file.name, tmp_file, "text/plain")})

        assert response.status_code == 200
        assert response.json() == {
            "status": "Success",
            "message": "Files have been successfully ingested and embeddings created.",
            "metadata": {
                "documents": [tmp_file.name]
            }
        }


def test_success_get_documents(test_client, mocker):
    """
    Test the successful retrieval of documents from the server.
    This test verifies that the `/documents` endpoint returns a 200 status code
    and the expected JSON response containing a list of documents.
    Args:
        test_client (TestClient): A test client instance for making HTTP requests.
        mocker (MockerFixture): A mocker fixture for patching and mocking dependencies.
    Mocks:
        - `app.server.get_document_from_vectordb`: Mocked to return a list of documents.
    Assertions:
        - The response status code is 200.
        - The response JSON contains a "status" key with the value "Success".
        - The response JSON contains a "metadata" key with a "documents" list matching the mocked documents.
    """

    mock_documents = ["test1.txt", "test2.pdf"]
    mocker.patch('app.server.get_document_from_vectordb', return_value=mock_documents)

    response = test_client.get("/documents")

    assert response.status_code == 200
    assert response.json() == {
        "status": "Success",
        "metadata": {"documents": mock_documents}
    }


def test_delete_embedding_success(test_client, mocker):
    """
    Test the successful deletion of an embedding from the vector database.
    This test verifies that the `delete_embedding_from_vectordb` function is called
    and the API endpoint for deleting a document responds with the expected status code.
    Args:
        test_client: A test client instance for simulating HTTP requests to the server.
        mocker: A mocking library instance used to patch and mock dependencies.
    Mocks:
        - `app.server.delete_embedding_from_vectordb`: Mocked to return `True`.
    Assertions:
        - Ensures that the HTTP DELETE request to the "/documents" endpoint with
          the specified parameters returns a status code of HTTPStatus.NO_CONTENT.
    """

    mocker.patch('app.server.delete_embedding_from_vectordb', return_value=True)

    response = test_client.delete("/documents", params={"document": "test1.txt"})

    assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_all_embedding_success(test_client, mocker):
    """
    Test the successful deletion of all embeddings from the vector database.
    This test verifies that the endpoint for deleting all documents functions
    correctly by mocking the `delete_embedding_from_vectordb` function to
    return `True` and asserting that the response status code is `HTTPStatus.NO_CONTENT`.
    Args:
        test_client: A test client instance used to simulate HTTP requests to the server.
        mocker: A mocking utility used to patch the `delete_embedding_from_vectordb` function.
    Mocks:
        - `app.server.delete_embedding_from_vectordb`: Mocked to return `True`.
    Assertions:
        - The response status code is `HTTPStatus.NO_CONTENT` (204).
    """

    mocker.patch('app.server.delete_embedding_from_vectordb', return_value=True)

    response = test_client.delete("/documents", params={"delete_all": True})

    assert response.status_code == HTTPStatus.NO_CONTENT


def test_upload_unsupported_file(test_client):
    """
    Tests the upload of an unsupported file format to the server.
    This test verifies that the server returns a 400 status code and an appropriate
    error message when a file with an unsupported format (e.g., .html) is uploaded.
    Args:
        test_client: A test client instance used to simulate HTTP requests to the server.
    Raises:
        AssertionError: If the response status code is not 400 or the error message
                        does not match the expected output.
    """

    with tempfile.NamedTemporaryFile(delete=True, suffix=".html") as tmp_file:
        tmp_file.write(b"This is sample html file.")
        tmp_file.seek(0)

        response = test_client.post("/documents", files={"files": (tmp_file.name, tmp_file, "text/plain")})

        assert response.status_code == 400
        assert response.json() == {
            "detail": "Invalid file format. Please upload files in one of the following supported formats: pdf, txt, docx."
        }


def test_fail_get_documents(test_client, mocker):
    """
    Test case for handling failure when retrieving documents from the vector database.
    This test simulates an exception being raised during the retrieval of documents
    from the vector database and verifies that the server responds with the appropriate
    HTTP status code and error message.
    Args:
        test_client: A test client instance used to simulate HTTP requests to the server.
        mocker: A mocking library instance used to patch and simulate behavior of dependencies.
    Mocks:
        - `app.server.get_document_from_vectordb`: Mocked to raise an exception with the message "Error getting documents."
    Asserts:
        - The HTTP response status code is 500 (Internal Server Error).
        - The JSON response contains the expected error message.
    """

    mocker.patch('app.server.get_document_from_vectordb', side_effect=Exception("Error getting documents."))

    mock_logger = mocker.patch('app.server.logger')
    mock_logger.exception.return_value = None

    response = test_client.get("/documents")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Error getting documents."
    }


def test_delete_embedding_failure(test_client, mocker):
    """
    Test case for handling failure during the deletion of embeddings from the vector database.
    This test simulates a failure scenario where the `delete_embedding_from_vectordb` function
    raises an exception. It verifies that the server responds with the appropriate HTTP status
    code and error message.
    Args:
        test_client (TestClient): A test client instance for simulating HTTP requests to the server.
        mocker (MockerFixture): A fixture for mocking dependencies and functions.
    Mocks:
        - `app.server.delete_embedding_from_vectordb`: Mocked to raise an exception with the message "Error deleting embeddings."
    Asserts:
        - The response status code is 500 (Internal Server Error).
        - The response JSON contains the expected error detail message.
    """

    mocker.patch('app.server.delete_embedding_from_vectordb', side_effect=Exception("Error deleting embeddings."))

    mock_logger = mocker.patch('app.server.logger')
    mock_logger.exception.return_value = None

    response = test_client.delete("/documents", params={"document": "test1.txt"})

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Error deleting embeddings."
    }
