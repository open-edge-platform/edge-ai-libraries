#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import json
import base64
from unittest.mock import MagicMock

import numpy as np
from gstgva import VideoFrame
from gi.repository import Gst, GstVideo

from gvapython.mqtt_publisher.mqtt_publisher import MQTTPublisher


@pytest.fixture
def frame():
    mocked_frame = MagicMock(spec=VideoFrame)
    return mocked_frame

@pytest.fixture
def setup(mocker, monkeypatch):
    monkeypatch.setenv("MQTT_HOST", "x.x.x.x")
    monkeypatch.setenv("MQTT_PORT", "1883")

    mocker.patch('gvapython.mqtt_publisher.mqtt_publisher.MQTTClient')
    mqtt_pub_obj = MQTTPublisher()

    yield mqtt_pub_obj

class TestMQTTPublisher:

    
    # @pytest.mark.parametrize('publish_frame',
    #                          [False, True])
    # def test_process(self, mocker, setup, frame, publish_frame):
    #     Gst.init(None)
    #     mocked_gva_meta = MagicMock("gvapython.mqtt_publisher.mqtt_publisher.utils.get_gva_meta_messages")
    #     mocked_video_info = MagicMock(spec=GstVideo.VideoInfo)
    #     mocked_video_info.return_value = Gst.Caps.from_string("video/x-raw, width=(int)640, height=(int)480")
    #     mocked_video_info.to_caps.return_value.to_string.return_value = "video/x-raw, width=(int)640, height=(int)480"

    #     # frame.messages.return_value = [
    #     #     '{"key1": "value1"}', '{"key2": "value2"}'
    #     # ]
    #     frame.video_info.return_value = mocked_video_info

    #     mocker.patch('gvapython.mqtt_publisher.mqtt_publisher.utils.encode_frame', return_value=(np.array([[1, 2, 3], [4, 5, 6]]), "jpeg", 85, np.array([[2, 3, 4], [4, 6, 7]])))

    #     mqtt_pub_obj = setup
    #     mqtt_pub_obj.publish_frame = publish_frame
    #     mqtt_pub_obj.process(frame)

    #     frame = np.array([[1, 2, 3], [4, 5, 6]])
    #     metadata = {'key1': 'value1', 'key2': 'value2', 'frame_id':0}
    #     if publish_frame:
    #         expected_payload = (metadata,
    #                             base64.b64encode(frame).decode('utf-8'))
    #         mqtt_pub_obj.client.publish.assert_called_with(
    #             "edge_video_analytics_results", payload=json.dumps(expected_payload))
    #     else:
    #         mqtt_pub_obj.client.publish.assert_called_with(
    #             "edge_video_analytics_results", payload=json.dumps(metadata))
    #     #===========


    def test_broker_not_connected(self, caplog, setup, frame):
        mqtt_pub_obj = setup
        mqtt_pub_obj.client.is_connected.return_value = False
        mqtt_pub_obj.process(frame)
        assert "Message not published" in caplog.text