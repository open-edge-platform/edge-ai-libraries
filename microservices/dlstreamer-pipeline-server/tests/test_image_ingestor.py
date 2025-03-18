#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import queue
from unittest.mock import MagicMock
import sys
import src.common.log
import json
import base64
from src.subscriber.image_ingestor import ImageIngestor

# Mock setup for publisher object creation
@pytest.fixture
def img_cfg(mocker):
    src.common.log.configure_logging('DEBUG', False)

    img_cfg = MagicMock()
    img_cfg.get_topics.return_value = ['sub_test']

    mocker.patch('src.subscriber.cam_ingestor.ctypes.CDLL')
    mocker.patch('src.subscriber.cam_ingestor.ctypes')
    mocker.patch('src.subscriber.cam_ingestor.th.Thread')

    yield img_cfg


# Subscriber object for tests
@pytest.fixture
def img_ing_obj(img_cfg):
    img_ing_obj = ImageIngestor(queue.Queue(), img_cfg)
    yield img_ing_obj


class TestImageIngestor:

    def test_init(self, img_cfg, capfd):
        img_ing_obj.__init__(img_cfg, queue.Queue())
    
    def test_start(self, mocker, img_ing_obj):
        mocked_thread = mocker.patch('src.subscriber.image_ingestor.th.Thread')
        img_ing_obj.start()
        assert mocked_thread.start.called_with('target=self._run')

    @pytest.mark.parametrize(
        'is_set, expected',
        [
            (True, False),  #Thread already stopped
            (False, True)  #Thread to be stopped
        ])
    def test_stop(self, mocker, img_ing_obj, is_set, expected):
        mocked_event = mocker.patch('src.subscriber.image_ingestor.th.Event')
        img_ing_obj.stop_ev = mocked_event
        img_ing_obj.stop_ev.is_set.return_value = is_set
        if not is_set:
            mocked_thread = mocker.patch("src.subscriber.image_ingestor.th.Thread")
            img_ing_obj.start()
        img_ing_obj.stop()
        assert img_ing_obj.stop_ev.set.called == expected

    def test_error_handler(self, mocker, img_ing_obj):
        mock_request_queue = MagicMock()
        mock_request_queue.empty.side_effect = [False, False, True]
        mock_request_queue.get_nowait.side_effect = [None, queue.Empty]
        img_ing_obj.request_queue = mock_request_queue
        img_ing_obj.log = MagicMock()
        img_ing_obj.done = False
        img_ing_obj.error_handler("Test error message")
        img_ing_obj.log.error.assert_called_once_with('Error in ingestor thread: Test error message')
        img_ing_obj.log.info.assert_called_once_with("clearing pending items from request queue...")
        assert img_ing_obj.done is True

    def test_run(self, mocker, img_ing_obj):
        mocked_event = mocker.patch('src.subscriber.image_ingestor.th.Event')
        img_ing_obj.stop_ev = mocked_event
        img_ing_obj.stop_ev.is_set.side_effect = [False, True]
        mock_request_queue = MagicMock()
        mock_request_queue.get.return_value = {"source": {"type": "file", "path": "test_image.jpg"}}
        mock_open_func = mocker.patch('builtins.open', mocker.mock_open(read_data=b'test_image_data'))
        mock_gst_buffer = mocker.patch('gi.repository.Gst.Buffer.new_allocate', return_value=MagicMock())
        mock_gst_sample = mocker.patch('gi.repository.Gst.Sample', return_value=MagicMock())
        mock_gst_queue = mocker.patch.object(img_ing_obj, 'gst_queue')
        mock_error_handler = mocker.patch.object(img_ing_obj, 'error_handler')
        img_ing_obj._run(mock_request_queue)
        mock_gst_buffer.assert_called_once_with(None, len(b'test_image_data'), None)
        mock_gst_sample.assert_called_once()
        mock_gst_queue.put.assert_called_once_with(mock_gst_sample())
        mock_error_handler.assert_not_called()

    def test_run_base64_image(self, mocker, img_ing_obj):
        mocked_event = mocker.patch('src.subscriber.image_ingestor.th.Event')
        img_ing_obj.stop_ev = mocked_event
        img_ing_obj.stop_ev.is_set.side_effect = [False, True]
        base64_str = base64.b64encode(b'test_image_data').decode('utf-8')
        mock_request_queue = MagicMock()
        mock_request_queue.get.return_value = {"source": {"type": "base64_image", "data": base64_str}}
        mock_gst_buffer = mocker.patch('gi.repository.Gst.Buffer.new_allocate', return_value=MagicMock())
        mock_gst_sample = mocker.patch('gi.repository.Gst.Sample', return_value=MagicMock())
        mock_gst_queue = mocker.patch.object(img_ing_obj, 'gst_queue')
        mock_error_handler = mocker.patch.object(img_ing_obj, 'error_handler')
        img_ing_obj._run(mock_request_queue)
        decoded_blob = base64.b64decode(base64_str)
        mock_gst_buffer.assert_called_once_with(None, len(decoded_blob), None)
        mock_gst_sample.assert_called_once()
        mock_gst_queue.put.assert_called_once_with(mock_gst_sample())
        mock_error_handler.assert_not_called()


    @pytest.mark.parametrize('exception, expected',
                             [(queue.Empty(), None)])
    def test_run_errors(self, mocker, caplog, img_ing_obj, exception, expected):
        mocked_event = mocker.patch('src.subscriber.image_ingestor.th.Event')
        img_ing_obj.stop_ev = mocked_event
        img_ing_obj.stop_ev.is_set.side_effect = [False, True]

        img_ing_obj.gst_queue.side_effect = exception
        img_ing_obj._run(img_ing_obj.gst_queue)
        if expected:
            assert expected in caplog.text

    def test_run_with_exception(self, mocker, img_ing_obj):
        mocked_event = mocker.patch('src.subscriber.image_ingestor.th.Event')
        img_ing_obj.stop_ev = mocked_event
        img_ing_obj.stop_ev.is_set.side_effect = [False, True]
        mock_request_queue = MagicMock()
        mock_request_queue.get_nowait.side_effect = Exception("Test exception")
        mock_error_handler = mocker.patch.object(img_ing_obj, 'error_handler')
        img_ing_obj.request_queue = mock_request_queue
        img_ing_obj.request_queue.empty.return_value = False
        img_ing_obj._run(mock_request_queue)