import pytest
from http import HTTPStatus

def test_get_documents(test_client):
    response = test_client.get("/documents")
    assert response.status_code == HTTPStatus.OK
    assert isinstance(response.json(), list)

def test_ingest_document(test_client,test_file):
    response = test_client.post("/documents", files=test_file,follow_redirects=True)
    assert response.status_code == HTTPStatus.OK

def test_ingest_unsupported_format(test_client,test_file):
    test_file["files"] = ("sample-file.pptx", test_file["files"][1])
    response = test_client.post("/documents", files=test_file,follow_redirects=True)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "Unsupported file format" in response.json()["detail"]


def test_delete_documents(test_client,test_file):
    test_file["files"] = ("sample-file.txt", test_file["files"][1])
    response = test_client.post("/documents", files=test_file,follow_redirects=True)
    assert response.status_code == HTTPStatus.OK

    response = test_client.get("/documents")
    assert response.status_code == HTTPStatus.OK

    response = test_client.delete("/documents", params={"bucket_name": "intel.gai.ragfiles", "file_name": response.json()[0]['file_name'],"delete_all":False})
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_delete_all_documents(test_client):
    response = test_client.delete("/documents", params={"bucket_name": "intel.gai.ragfiles", "delete_all": True})
    assert response.status_code == 204