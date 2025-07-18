#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import base64
import json
from unittest.mock import MagicMock

import pytest
import src

import src.common
from src.publisher.mqtt.mqtt_publisher import MQTTPublisher

@pytest.fixture
def setup(mocker):
    src.common.log.configure_logging('DEBUG')

    app_cfg = {
        'encoding': {
            'level': 95,
            'type': 'jpeg'
        },
        "mqtt_publisher": {
            "host": "localhost",
            "port": 1883,
            "topic": "test",
            "publish_frame": False,
        }
    }

    mocker.patch('src.publisher.mqtt.mqtt_publisher.MQTTClient')
    yield app_cfg


class TestMqttPublisher:

    def test_stop(self, mocker, setup):
        app_cfg = setup
        pub_obj = MQTTPublisher(app_cfg)
        mock_log_info = mocker.patch.object(pub_obj.log, 'info')
        pub_obj.start()
        pub_obj.stop()
        mock_log_info.assert_called_with('MQTT publisher thread stopped')
        assert pub_obj.th is None

    def test_error_handler(self, mocker, setup):
        app_cfg = setup
        pub_obj = MQTTPublisher(app_cfg)
        mock_log_error = mocker.patch.object(pub_obj.log, 'error')
        mock_stop = mocker.patch.object(pub_obj, 'stop')
        pub_obj.error_handler('Test error message')
        mock_log_error.assert_called_once_with('Error in MQTT thread: Test error message')
        mock_stop.assert_called_once()

    def test_run(self, mocker, setup):
        app_cfg = setup
        pub_obj = MQTTPublisher(app_cfg)
        mock_stop_ev = mocker.patch.object(pub_obj, 'stop_ev')
        mock_stop_ev.is_set.side_effect = [False, False, True] 
        mocker.patch.object(pub_obj, 'queue')
        mocker.patch.object(pub_obj, '_publish')
        mocker.patch('time.sleep', return_value=None)
        pub_obj._run()
        
    def test_publish_mqtt(self, setup):
        app_cfg = setup

        pub_obj = MQTTPublisher(app_cfg)
        pub_obj.client.is_connected.return_value = True
        pub_obj.filter = None

        frame = b"Test"
        metadata = {'key1': 'value1', 'key2': 'value1'}

        pub_obj._publish(frame, metadata)
        
        expected_payload = {
            "metadata": metadata,
            "blob": base64.b64encode(frame).decode('utf-8')
        }
        
        pub_obj.client.publish.assert_called_once()

    def test_broker_not_connected(self, capfd, setup):
        app_cfg = setup

        pub_obj = MQTTPublisher(app_cfg)
        pub_obj.client.is_connected.return_value = False

        frame = b"Test"
        metadata = {'key1': 'value1', 'key2': 'value1'}
        pub_obj._publish(frame, metadata)
       
        assert "Message not published" in capfd.readouterr().out

    # def test_filter(self, capfd, setup):
    #     app_cfg = setup
    #     app_cfg["mqtt_publisher"]["filter"] = {"type": "classification", "label_score": {"person": 0.5}}
    #     pub_obj = MQTTPublisher(app_cfg)

    #     frame = b"Test"
    #     metadata = {'key1': 'value1', 'key2': 'value1'}
    #     pub_obj._publish(frame, metadata)
       
    #     assert "Filter criteria not met" in capfd.readouterr().out