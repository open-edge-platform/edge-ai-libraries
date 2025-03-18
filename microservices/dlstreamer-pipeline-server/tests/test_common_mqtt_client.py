#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock
from utils.mqtt_client import MQTTClient

@pytest.fixture
def setup(mocker):
    mocker.patch('utils.mqtt_client.mqtt.Client')
    host = "x.x.x.x"
    port = 1883
    mqtt_client = MQTTClient(host, port)
    mqtt_client.log.setLevel('DEBUG')

    return mqtt_client

class TestMqttClient:

    def test_init(self, setup):
        host = "x.x.x.x"
        port = 1883
        tls = {"ca_cert": "ca.crt", "client_key": "client.key", "client_cert": "client.crt"}

        mqtt_client = MQTTClient(host, port, tls_config=tls)
        mqtt_client.client.tls_set.assert_called_with('ca.crt', 'client.crt', 'client.key')

    def test_publish(self, setup):
        mqtt_client = setup
        mqtt_client.publish("test", "hello")

        mqtt_client.client.publish.assert_called_with(topic='test', payload='hello', qos=0)
    
    def test_is_connected(self, setup):
        mqtt_client = setup
        mqtt_client.is_connected()

        assert mqtt_client.client.is_connected.assert_called

    def test_on_disconnect(self, caplog, setup):
        mqtt_client = setup
        mqtt_client.on_disconnect("client", None, None)

        assert "Client disconnected" in caplog.text
    
    def test_on_log(self, caplog, setup):
        mqtt_client = setup
        mqtt_client.on_log("client", None, None, "Test")

        assert "Test" in caplog.text

    def test_on_connect(self, caplog, setup):
        mqtt_client = setup
        mqtt_client.on_connect("client", None, None, 0)
        assert "successful" in caplog.text
        mqtt_client.on_connect("client", None, None, 1)
        assert "error" in caplog.text
    
    def test_on_publish(self, caplog, setup):
        mqtt_client = setup
        mqtt_client.on_publish("client", None, 20)

        assert "Message published" in caplog.text

    @pytest.mark.parametrize(
        'host, expected',
        [('10.23.42.123', None),
         ('10.243', ValueError),
         ('10',ValueError),
         ('abc.com',None),
         ('a12-bc', None),
         ('-a12bc', ValueError),
         ('2001:0db8:85a3:0000:0000:8a2e:0370:7334', None),
        ])
    def test_valid_host(self, setup, host, expected):
        mqtt_client = setup
        mqtt_client.host = host

        try:
            mqtt_client.invalid_host()
        except Exception as e:
            assert type(e) == expected