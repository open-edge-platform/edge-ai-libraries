# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace

import pytest

from src import batch_event_subscriber as subscriber


class FakeClient:
    def __init__(
        self,
        callback_api_version=None,
        userdata=None,
        manual_ack=False,
        client_id="",
        clean_session=None,
    ):
        self.userdata = userdata or {}
        self.manual_ack = manual_ack
        self.client_id = client_id
        self.clean_session = clean_session
        self.calls = []
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None

    def subscribe(self, topic, qos):
        self.calls.append(("subscribe", topic, qos))
        return subscriber.mqtt.MQTT_ERR_SUCCESS, 1

    def ack(self, mid, qos):
        self.calls.append(("ack", mid, qos))
        return subscriber.mqtt.MQTT_ERR_SUCCESS

    def username_pw_set(self, username, password):
        self.calls.append(("auth", username, password))

    def reconnect_delay_set(self, min_delay, max_delay):
        self.calls.append(("reconnect", min_delay, max_delay))

    def connect_async(self, host, port, keepalive):
        self.calls.append(("connect", host, port, keepalive))

    def loop_forever(self, retry_first_connection=False):
        return None


def _payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "run_id": "detect-7",
        "status": "completed",
        "device": "camera-west",
        "video_filename": "inspection.mp4",
        "start_id": 10,
        "end_id": 20,
        "pipeline_status": "COMPLETED",
        "error": None,
    }
    payload.update(overrides)
    return payload


def _message(payload, *, mid=42, qos=1):
    return SimpleNamespace(
        payload=json.dumps(payload).encode(),
        mid=mid,
        qos=qos,
    )


def test_batch_event_validates_completed_range():
    event = subscriber.BatchEvent.from_payload(_payload())

    assert event.run_id == "detect-7"
    assert (event.start_id, event.end_id) == (10, 20)

    with pytest.raises(subscriber.InvalidBatchEvent, match="less than"):
        subscriber.BatchEvent.from_payload(_payload(start_id=20, end_id=20))


@pytest.mark.parametrize(
    "change",
    [
        {"status": "running"},
        {"schema_version": "2.0"},
        {"run_id": ""},
        {"start_id": -1},
        {"end_id": True},
        {"start_id": "10"},
        {"end_id": 20.0},
    ],
)
def test_batch_event_rejects_invalid_contract(change):
    with pytest.raises(subscriber.InvalidBatchEvent):
        subscriber.BatchEvent.from_payload(_payload(**change))


def test_valid_delivery_is_deferred_to_callback(monkeypatch):
    client = FakeClient()
    received = []
    monkeypatch.setattr(subscriber, "_on_batch_callback", lambda *args: received.append(args))

    subscriber._on_message(
        client,
        {"max_payload_bytes": 4096},
        _message(_payload()),
    )

    assert len(received) == 1
    event, delivery = received[0]
    assert event.run_id == "detect-7"
    assert client.calls == []
    assert delivery.acknowledge() is True
    assert client.calls == [("ack", 42, 1)]


def test_invalid_delivery_is_acknowledged_as_poison_message():
    client = FakeClient()

    subscriber._on_message(
        client,
        {"max_payload_bytes": 4096},
        _message(_payload(status="running")),
    )

    assert client.calls == [("ack", 42, 1)]


def test_oversized_delivery_is_acknowledged():
    client = FakeClient()

    subscriber._on_message(
        client,
        {"max_payload_bytes": 2},
        _message(_payload()),
    )

    assert client.calls == [("ack", 42, 1)]


def test_subscriber_reuses_broker_security_with_distinct_client(monkeypatch):
    clients = []
    settings = SimpleNamespace(
        mqtt_enabled=True,
        mqtt_host="broker.example.test",
        mqtt_port=8883,
        mqtt_batch_topic="apm/batch-complete",
        mqtt_qos=2,
        mqtt_keepalive=90,
        mqtt_max_payload_bytes=8192,
        mqtt_batch_client_id="aqh-batch-1",
        mqtt_username="agent",
        mqtt_password="secret",
    )

    def create_client(*args, **kwargs):
        client = FakeClient(*args, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(subscriber.mqtt, "Client", create_client)
    monkeypatch.setattr(
        subscriber.threading,
        "Thread",
        lambda **kwargs: SimpleNamespace(start=lambda: None),
    )

    client = subscriber.start_subscriber(settings)

    assert client is clients[0]
    assert client.client_id == "aqh-batch-1"
    assert client.manual_ack is True
    assert client.clean_session is False
    assert client.userdata == {
        "topic": "apm/batch-complete",
        "qos": 2,
        "max_payload_bytes": 8192,
    }
    assert client.calls == [
        ("reconnect", 1, 120),
        ("auth", "agent", "secret"),
        ("connect", "broker.example.test", 8883, 90),
    ]
