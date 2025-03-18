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

from src.subscriber.cam_ingestor import XirisCamIngestor

# Mock setup for publisher object creation
@pytest.fixture
def cam_ing_cfg(mocker):
    src.common.log.configure_logging('DEBUG', False)
    cam_ing_cfg = {
        'xiris': {
            'ip_address': '192.168.1.1',
            'shutter_mode': 1,
            'frame_rate': 30,
            'pixel_depth': 8,
            'flip_mode': 0,
            'set_sharpen': 1,
            'focus': 50,
            'tone_map_curve_type': 2,
            'tone_map_curve_value': 0.5,
            'exposure_time': 1000,
            'auto_exposure_mode': 1,
            'pilot_light_on': 1,
            'pilot_light_power': 100
        }
    }

    mocker.patch('src.subscriber.cam_ingestor.ctypes.CDLL')
    mocker.patch('src.subscriber.cam_ingestor.ctypes')

    yield cam_ing_cfg


# Subscriber object for tests
@pytest.fixture
def cam_ing_obj(cam_ing_cfg):
    cam_ing_obj = XirisCamIngestor(queue.Queue(), cam_ing_cfg)
    yield cam_ing_obj


class TestCamIngestor:

    def test_init(self, cam_ing_cfg, capfd):
        cam_ing_obj.__init__(queue.Queue(), cam_ing_cfg)

    def test_start(self, mocker, cam_ing_obj):
        mocked_thread = mocker.patch('src.subscriber.cam_ingestor.th.Thread')
        cam_ing_obj.start()
        assert mocked_thread.start.called_with('target=self._run')

    def test_camera_start(self, mocker, cam_ing_obj):
        # mocked_thread = mocker.patch('src.subscriber.cam_ingestor.th.Thread')
        cam_ing_obj.camera_start()
        # assert mocked_thread.start.called_with('target=self._run')

    def test_error_handler(self, mocker, cam_ing_obj):
        # mocked_thread = mocker.patch('src.subscriber.cam_ingestor.th.Thread')
        cam_ing_obj.error_handler("msg")

    def test_signal_handler(self, mocker, cam_ing_obj):
        # mocked_thread = mocker.patch('src.subscriber.cam_ingestor.th.Thread')
        cam_ing_obj.signal_handler()

    @pytest.mark.parametrize(
        'is_set, expected',
        [
            (True, False),  #Thread already stopped
            (False, True)  #Thread to be stopped
        ])
    def test_stop(self, mocker, cam_ing_obj, is_set, expected):
        mocked_event = mocker.patch('src.subscriber.cam_ingestor.th.Event')
        cam_ing_obj.stop_ev = mocked_event
        cam_ing_obj.stop_ev.is_set.return_value = is_set
        if not is_set:
            mocked_thread = mocker.patch("src.subscriber.cam_ingestor.th.Thread")
            cam_ing_obj.start()
        cam_ing_obj.stop()
        assert cam_ing_obj.stop_ev.set.called == expected

    def test_run(self, mocker, cam_ing_obj):
        mock_stop_ev = mocker.patch.object(cam_ing_obj, 'stop_ev')
        mock_stop_ev.is_set.side_effect = [False, True]
        mock_res = MagicMock()
        mock_res.height = 480
        mock_res.width = 640
        mock_res.channels = 3
        mock_res.bit_depth = 8
        mock_res.data = b'\x00' * (480 * 640 * 3)
        mocker.patch.object(cam_ing_obj.lib, 'get_frame', return_value=mock_res)
        mock_gst_buffer = mocker.patch('gi.repository.Gst.Buffer.new_allocate', return_value=MagicMock())
        mock_gst_sample = mocker.patch('gi.repository.Gst.Sample', return_value=MagicMock())
        mock_queue = mocker.patch.object(cam_ing_obj, 'queue')
        mock_error_handler = mocker.patch.object(cam_ing_obj, 'error_handler')
        cam_ing_obj._run()
        mock_gst_buffer.assert_called_once_with(None, len(mock_res.data), None)
        mock_gst_sample.assert_called_once()
        mock_queue.put.assert_called_once_with(mock_gst_sample())
        mock_error_handler.assert_not_called()

    @pytest.mark.parametrize('exception, expected',
                             [(RuntimeError(), 'Error in ingestor thread'),
                              (queue.Empty(), None)])
    def test_run_errors(self, mocker, caplog, cam_ing_obj, exception, expected):
        mocked_event = mocker.patch('src.subscriber.cam_ingestor.th.Event')
        cam_ing_obj.stop_ev = mocked_event
        cam_ing_obj.stop_ev.is_set.side_effect = [False, True]

        cam_ing_obj.lib.get_frame().side_effect = exception
        cam_ing_obj._run()
        # if expected:
        #     assert expected in caplog.text