#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import cv2
from unittest.mock import MagicMock
from gstgva.video_frame import VideoFrame
import utils.publisher_utils as utils


class TestUtils:

    @pytest.mark.parametrize('app_cfg, frame, height, width, expected',
                             [({
                                 'encoding': {
                                     'level': 95,
                                     'type': 'jpeg'
                                 }
                             }, bytes(range(12)), 2, 2, True),
                              ({
                                  'encoding': {
                                      'level': 5,
                                      'type': 'png'
                                  }
                              }, bytes(range(27)), 3, 3, True),
                              ({
                                  'encoding': {
                                      'level': 5,
                                      'type': 'png'
                                  }
                              }, bytes(range(1)), 3, 3, ValueError),
                              ({
                                  'encoding': {
                                      'level': 5,
                                      'type': 'jpeg'
                                  }
                              }, bytes(range(12)), 2, 2, cv2.error),
                              ({}, bytes(range(12)), 2, 2, True)])
    def test_encode_frame(self, mocker, app_cfg, frame, height, width,
                          expected):
        enc_type = None
        enc_level = None

        if app_cfg:
            enc_type = app_cfg['encoding']['type']
            enc_level = app_cfg['encoding']['level']
        if expected == cv2.error:
            mocker.patch('cv2.imencode', side_effect=cv2.error)
        try:
            frame, enc_type, enc_level = utils.encode_frame(
                enc_type, enc_level, frame, height, width, 3)
            assert frame[0] == expected
        except Exception as e:
            if expected == TypeError:
                assert expected == type(e)

    @pytest.mark.parametrize('detection', [True, False])
    def test_gva_meta_regions(self, detection):
        mocked_result = MagicMock(spec=VideoFrame)
        #Mocked regions
        rect = MagicMock()
        rect.configure_mock(x=150, y=60, w=50, h=90)
        tensor = MagicMock()
        tensor.name.return_value = "tensor1"
        tensor.confidence.return_value = 0.8
        tensor.label_id.return_value = 1
        tensor.is_detection.return_value = detection
        tensor.label.return_value = "person"

        region = MagicMock()
        region.label.return_value = 'vehicle'
        region.rect.return_value = rect
        region.tensors.return_value = [tensor]
        region.object_id = MagicMock(return_value="object_id1")
        mocked_result.regions.return_value = [region]

        gva_meta = utils.get_gva_meta_regions(mocked_result)
        if not detection:
            assert gva_meta == [{
                'x':
                    150,
                'y':
                    60,
                'width':
                    50,
                'height':
                    90,
                'object_id':
                    "object_id1",
                'tensor': [{
                    'name': 'tensor1',
                    'confidence': 0.8,
                    'label_id': 1,
                    'label': 'person'
                }]
            }]
        else:
            assert gva_meta == [{
                'x':
                    150,
                'y':
                    60,
                'width':
                    50,
                'height':
                    90,
                'object_id':
                    "object_id1",
                'tensor': [{
                    'name': 'tensor1',
                    'confidence': 0.8,
                    'label_id': 1,
                    'label': 'vehicle'
                }]
            }]

    def test_get_gva_meta_messages(self):
        mocked_frame = MagicMock(spec=VideoFrame)
        mocked_frame.messages.return_value = [
            '{"key1": "value1"}', '{"key2": "value2"}'
        ]
        meta_data = {}
        utils.get_gva_meta_messages(mocked_frame, meta_data)
        assert meta_data['key1'] == 'value1' and meta_data['key2'] == 'value2'
