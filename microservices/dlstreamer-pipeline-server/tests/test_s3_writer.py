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
from src.publisher.s3.s3_writer import S3Writer

@pytest.fixture
def setup(mocker):
    src.common.log.configure_logging('DEBUG')

    app_cfg = {
        "S3_write": {
            "bucket": "dlstreamer_pipeline_server",
            "folder_prefix": 1883,
            "block": False
        }
    }

    mocker.patch('src.publisher.s3.s3_writer.S3Client')
    yield app_cfg

class TestS3Writer:
    def test_stop(self, mocker, setup):
        app_cfg = setup
        s3_obj = S3Writer(app_cfg)
        mock_log_info = mocker.patch.object(s3_obj.log, 'info')
        s3_obj.start()
        s3_obj.stop()
        mock_log_info.assert_called_with('S3 writer thread stopped')
        assert s3_obj.th is None

    def test_error_handler(self, mocker, setup):
        app_cfg = setup
        s3_obj = S3Writer(app_cfg)
        mock_log_error = mocker.patch.object(s3_obj.log, 'error')
        mock_stop = mocker.patch.object(s3_obj, 'stop')
        s3_obj.error_handler('Test error message')
        mock_log_error.assert_called_once_with('Error in S3 thread: Test error message')
        mock_stop.assert_called_once()

    def test_run(self, mocker, setup):
        app_cfg = setup
        s3_obj = S3Writer(app_cfg)
        mock_stop_ev = mocker.patch.object(s3_obj, 'stop_ev')
        mock_stop_ev.is_set.side_effect = [False, False, True] 
        mocker.patch.object(s3_obj, 'queue')
        mocker.patch.object(s3_obj, '_publish')
        mocker.patch('time.sleep', return_value=None)
        s3_obj._run()
        
    # def test_fetch_data(mocker):
    #     mock_response = {"key": "mocked value"}

    #     with mocker.patch("requests.get", return_value=mocker.Mock(json=lambda: mock_response)):
    #         result = fetch_data()
        
    #     assert result == mock_response
