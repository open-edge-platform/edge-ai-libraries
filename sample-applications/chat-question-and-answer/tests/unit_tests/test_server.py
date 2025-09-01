def test_query_chain_successful_response(test_client, mocker):
    payload = {"input": "What is AI?"}
    mocker.patch("app.server.process_chunks", return_value=iter(["one", "two"]))
    response = test_client.post("/chat", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    streamed_data = ""
    for chunk in response.iter_text():
        streamed_data += chunk
    
    assert "one" in streamed_data
    assert "two" in streamed_data

def test_query_chain_no_input(test_client):
    payload = {"input": ""}
    response = test_client.post("/chat", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Question is required"}

def test_query_chain_invalid_json(test_client):
    response = test_client.post("/chat", content="invalid json")
    assert response.status_code == 422

def test_root(test_client):
    response = test_client.get("/")
    assert response.status_code == 200

def test_docs(test_client):
    response = test_client.get("/docs")
    assert response.status_code == 200
