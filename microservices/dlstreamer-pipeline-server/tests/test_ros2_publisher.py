#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import threading
import time
from unittest import mock

# Prepare rclpy, Node, String mocks before import
rclpy_mock = mock.MagicMock()
node_constructor_mock = mock.MagicMock()
node_instance_mock = mock.MagicMock()
publisher_mock = mock.MagicMock()

node_constructor_mock.return_value = node_instance_mock
node_instance_mock.create_publisher.return_value = publisher_mock

string_mock = mock.MagicMock()

with mock.patch.dict('sys.modules', {
    'rclpy': rclpy_mock,
    'rclpy.node': mock.MagicMock(Node=node_constructor_mock),
    'std_msgs.msg': mock.MagicMock(String=string_mock)
}):
    from src.publisher.ros2.ros2_publisher import ROS2Publisher


@pytest.fixture
def ros2_publisher():
    rclpy_mock.ok.return_value = False  # force init
    config = {"topic": "/test_topic", "publish_frame": True}
    pub = ROS2Publisher(config)
    yield pub
    pub.stop_ev.set()
    if hasattr(pub, 'th') and pub.th:
        pub.th.join()

def test_init_calls_rclpy_ok_and_init():
    rclpy_mock.ok.return_value = False
    config = {"topic": "/test_topic"}
    publisher = ROS2Publisher(config)
    rclpy_mock.init.assert_called_once()
    # Check Node and publisher assigned correctly
    assert publisher.node == node_instance_mock
    assert publisher.publisher == publisher_mock

def test_start_creates_thread(ros2_publisher):
    ros2_publisher.start()
    time.sleep(0.01)
    assert ros2_publisher.th.is_alive()
    ros2_publisher.stop()

def test_stop_cleans_up(ros2_publisher):
    ros2_publisher.start()
    time.sleep(0.01)
    ros2_publisher.stop()
    assert ros2_publisher.th is None
    assert node_instance_mock.destroy_node.call_count >= 1

def test_error_handler_logs_and_stops(ros2_publisher):
    with mock.patch.object(ros2_publisher, 'stop') as stop_mock:
        ros2_publisher.error_handler("some error")
        stop_mock.assert_called_once()

def test_publish_with_frame(ros2_publisher):
    ros2_publisher.publish_frame = True
    ros2_publisher._publish(b'test', {"meta": "data"})
    assert publisher_mock.publish.called
    data_str = publisher_mock.publish.call_args[0][0].data
    assert '"meta": "data"' in data_str
    assert "blob" in data_str

def test_publish_without_frame(ros2_publisher):
    ros2_publisher.publish_frame = False
    ros2_publisher._publish(b'test', {"meta": "data"})
    data_str = publisher_mock.publish.call_args[0][0].data
    assert '"blob": ""' in data_str

def test_run_handles_empty_queue(ros2_publisher):
    ros2_publisher.stop_ev.clear()
    thread = threading.Thread(target=ros2_publisher._run)
    thread.start()
    time.sleep(0.01)
    ros2_publisher.stop_ev.set()
    thread.join()

# def test_run_handles_exception(ros2_publisher):
#     ros2_publisher.stop_ev.clear()
#     with mock.patch.object(ros2_publisher, '_publish', side_effect=Exception("fail")):
#         ros2_publisher.queue.append((b'frame', {"m":1}))
#         thread = threading.Thread(target=ros2_publisher._run)
#         thread.start()
#         time.sleep(0.01)
#         ros2_publisher.stop_ev.set()
#         thread.join()
