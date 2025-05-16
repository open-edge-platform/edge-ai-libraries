#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock
from src.publisher.eis.grpc_publisher import EdgeGrpcPublisher
import src.common.log


@pytest.fixture
def pub_cfg(mocker):
    src.common.log.configure_logging('DEBUG', False)
    mocker.patch('src.publisher.eis.grpc_publisher.th')
    mocker.patch('src.publisher.eis.grpc_publisher.Client')
    
    pub_cfg = MagicMock()
    pub_cfg.get_endpoint.return_value = "localhost:50051"
    pub_cfg.get_interface_value.side_effect = lambda key: "true" if key == "overlay_annotation" else KeyError

    yield pub_cfg

@pytest.fixture
def pub_topic():
    return "test_topic"

@pytest.fixture
def edge_grpc_publisher(pub_cfg, pub_topic):
    yield EdgeGrpcPublisher(pub_cfg, pub_topic)

class TestEdgeGrpcPublisher:
    def test_initialization(self,edge_grpc_publisher):
        assert edge_grpc_publisher.topic == "test_topic"
        assert edge_grpc_publisher.host == "localhost"
        assert edge_grpc_publisher.overlay_annotation == True

    def test_overlay_annotation_exception(self,pub_cfg, pub_topic, mocker):
        pub_cfg.get_interface_value.side_effect = Exception("Test Exception")
        mocker.patch('src.publisher.eis.grpc_publisher.get_logger')
        edge_grpc_publisher = EdgeGrpcPublisher(pub_cfg, pub_topic)
        assert edge_grpc_publisher.overlay_annotation is False
        edge_grpc_publisher.log.debug.assert_any_call("Exception while parsing config".format("Test Exception"))
        edge_grpc_publisher.log.info.assert_any_call('overlay annotation enabled: False')
        
    def test_start(self,edge_grpc_publisher):
        edge_grpc_publisher.start()
        assert edge_grpc_publisher.th is not None

    def test_edge_grpc_publisher_stop(self,edge_grpc_publisher, mocker):
        mock_thread = mocker.Mock()
        edge_grpc_publisher.th = mock_thread
        edge_grpc_publisher.stop_ev = mocker.Mock()
        edge_grpc_publisher.stop_ev.set.return_value = False
        edge_grpc_publisher.stop()
        if mock_thread is not None:
            mock_thread.join.assert_called_once()
        assert edge_grpc_publisher.th is None

    def test_run(self, edge_grpc_publisher, mocker):
        frame = b"test_frame"
        meta_data = {"key": "value"}
        edge_grpc_publisher.queue.append((frame, meta_data))
        edge_grpc_publisher.stop_ev.is_set.return_value = False
        mocker.patch.object(edge_grpc_publisher, '_publish')
        mocker.patch.object(edge_grpc_publisher.log, 'info')
        mocker.patch.object(edge_grpc_publisher.log, 'debug')
        def stop_after_one_iteration():
            edge_grpc_publisher.stop_ev.is_set.return_value = True
        edge_grpc_publisher._publish.side_effect = stop_after_one_iteration
        edge_grpc_publisher._run()
        edge_grpc_publisher._publish.assert_called_once_with(frame, meta_data)
        edge_grpc_publisher.log.info.assert_called_once_with("Publish thread started")
        edge_grpc_publisher.log.debug.assert_not_called()

    def test_run_indexerror(self, edge_grpc_publisher, mocker):
        mocker.patch('time.sleep', return_value=None)
        edge_grpc_publisher.log = MagicMock()
        edge_grpc_publisher.stop_ev = MagicMock()
        edge_grpc_publisher.stop_ev.is_set.side_effect = [False, False, True]
        edge_grpc_publisher._publish = MagicMock()
        frame = "test_frame"
        meta_data = "test_meta_data"
        edge_grpc_publisher.queue.append((frame, meta_data))
        edge_grpc_publisher._run()
        edge_grpc_publisher.log.info.assert_any_call("Publish thread started")
        edge_grpc_publisher.log.debug.assert_any_call("No data in client queue")

    def test_publish(self, edge_grpc_publisher, mocker):
        frame = b"test_frame"
        meta_data = {"key": "value"}
        async def mock_send(msg, frame):
            return None
        mocker.patch.object(edge_grpc_publisher.publisher, 'send', side_effect=mock_send)
        mocker.patch.object(edge_grpc_publisher.log, 'info')
        edge_grpc_publisher._publish(frame, meta_data)
        edge_grpc_publisher.publisher.send.assert_called_once_with(meta_data, frame)
        edge_grpc_publisher.log.info.assert_called_once_with('Published message: {} to topic: {} for client {}'.format(meta_data, edge_grpc_publisher.topic, edge_grpc_publisher.host))

    def test_edge_grpc_publisher_close(self, edge_grpc_publisher):
        edge_grpc_publisher.close()
        assert not hasattr(edge_grpc_publisher, 'publisher')