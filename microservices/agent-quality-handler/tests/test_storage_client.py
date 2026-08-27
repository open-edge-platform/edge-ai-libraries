# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest
import requests

from src.utility import storage_client


class FakeResponse:
    def __init__(self, status_code=200, data=None, error=None):
        self.status_code = status_code
        self._data = data
        self._error = error

    def json(self):
        if self._error:
            raise self._error
        return self._data


@pytest.fixture
def client():
    return storage_client.StorageClient(
        base_url="http://storage.example.test/api",
        connect_timeout_seconds=2.0,
        read_timeout_seconds=7.0,
        read_max_attempts=3,
        retry_backoff_seconds=0.1,
    )


def test_get_detections_sends_contract_parameters(monkeypatch, client):
    request = {}

    def get(url, **kwargs):
        request.update(url=url, **kwargs)
        return FakeResponse(data=[{"label": "dent"}])

    monkeypatch.setattr(storage_client.requests, "get", get)

    result = client.get_detections(
        label="dent", min_confidence=0.75, limit=25, min_id=10, max_id=20
    )

    assert result == [{"label": "dent"}]
    assert request == {
        "url": "http://storage.example.test/api/detections",
        "params": {
            "label": "dent",
            "min_confidence": 0.75,
            "limit": 25,
            "min_id": 10,
            "max_id": 20,
        },
        "timeout": (2.0, 7.0),
        "proxies": {"http": None, "https": None},
    }


def test_transient_read_failures_are_retried(monkeypatch, client):
    responses = [
        requests.ConnectionError("offline"),
        FakeResponse(status_code=503),
        FakeResponse(data={"by_class": []}),
    ]
    delays = []

    def get(*args, **kwargs):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(storage_client.requests, "get", get)
    monkeypatch.setattr(storage_client.time, "sleep", delays.append)

    assert client.get_summary(min_id=10, max_id=20) == {"by_class": []}
    assert delays == [0.1, 0.2]
    assert responses == []


def test_permanent_read_failure_is_not_retried(monkeypatch, client):
    calls = []

    def get(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse(status_code=400)

    monkeypatch.setattr(storage_client.requests, "get", get)

    with pytest.raises(storage_client.StorageHTTPError) as exc_info:
        client.get_summary()

    assert exc_info.value.status_code == 400
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("method", "response", "message"),
    [
        ("get_summary", FakeResponse(data=[]), "must be a JSON object"),
        ("get_detections", FakeResponse(data={}), "must be a JSON array"),
        ("get_summary", FakeResponse(error=ValueError("bad JSON")), "not valid JSON"),
    ],
)
def test_invalid_storage_responses_raise_contract_errors(
    monkeypatch, client, method, response, message
):
    monkeypatch.setattr(storage_client.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(storage_client.StorageContractError, match=message):
        getattr(client, method)()


def test_module_facade_uses_runtime_settings(monkeypatch):
    settings = SimpleNamespace(
        storage_service_url="http://storage.example.test",
        storage_connect_timeout_seconds=1.0,
        storage_read_timeout_seconds=4.0,
        storage_read_max_attempts=2,
        storage_retry_backoff_seconds=0.0,
    )
    monkeypatch.setattr(storage_client, "load_runtime_settings", lambda: settings)
    monkeypatch.setattr(
        storage_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(data={"by_class": []}),
    )

    assert storage_client.get_summary(10, 20) == {"by_class": []}
