import tempfile
from http import HTTPStatus


def test_chain_response(test_client, mocker):

    payload = {"input": "What is AI?", "stream": True}

    mocker.patch("app.server.process_query", return_value=iter(["one", "two"]))

    response = test_client.post("/stream_log", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    streamed_data = ""
    for chunk in response.iter_text():
        streamed_data += chunk

    assert "one" in streamed_data
    assert "two" in streamed_data


def test_success_upload_and_create_embedding(test_client, mocker):
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
    mock_documents = ["test1.txt", "test2.pdf"]
    mocker.patch('app.server.get_document_from_vectordb', return_value=mock_documents)

    response = test_client.get("/documents")

    assert response.status_code == 200
    assert response.json() == {
        "status": "Success",
        "metadata": {"documents": mock_documents}
    }


def test_delete_embedding_success(test_client, mocker):
    mocker.patch('app.server.delete_embedding_from_vectordb', return_value=True)

    response = test_client.delete("/documents", params={"document": "test1.txt"})

    assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_all_embedding_success(test_client, mocker):
    mocker.patch('app.server.delete_embedding_from_vectordb', return_value=True)

    response = test_client.delete("/documents", params={"delete_all": True})

    assert response.status_code == HTTPStatus.NO_CONTENT


def test_upload_unsupported_file(test_client):
    with tempfile.NamedTemporaryFile(delete=True, suffix=".html") as tmp_file:
        tmp_file.write(b"This is sample html file.")
        tmp_file.seek(0)

        response = test_client.post("/documents", files={"files": (tmp_file.name, tmp_file, "text/plain")})

        assert response.status_code == 400
        assert response.json() == {
            "detail": "Invalid file format. Please upload files in one of the following supported formats: pdf, txt, docx."
        }


def test_fail_get_documents(test_client, mocker):
    mocker.patch('app.server.get_document_from_vectordb', side_effect=Exception("Error getting documents."))

    response = test_client.get("/documents")

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Error getting documents."
}


def test_delete_embedding_failure(test_client, mocker):
    mocker.patch('app.server.delete_embedding_from_vectordb', side_effect=Exception("Error deleting embeddings."))

    response = test_client.delete("/documents", params={"document": "test1.txt"})

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Error deleting embeddings."
    }
