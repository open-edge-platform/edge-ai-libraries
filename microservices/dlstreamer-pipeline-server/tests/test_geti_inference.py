#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import sys
import pytest
import numpy as np
from unittest.mock import MagicMock

from gstgva import VideoFrame

sys.modules['geti_sdk.deployment'] = MagicMock()
geti_inference = pytest.importorskip("gvapython.geti.object_detection.geti_inference")


@pytest.fixture
def frame():
    mocked_frame = MagicMock(spec=VideoFrame)
    return mocked_frame


@pytest.fixture
def predictions():

    class Predictions:

        def deidentify(self):
            pass

        def to_dict(self):
            return {
                'annotations': [{
                    'shape': {
                        'x': 50,
                        'y': 50,
                        'width': 100,
                        'height': 100,
                    },
                    'labels': [{
                        'name': 'box',
                        'probability': 0.75
                    }]
                }, {
                    'shape': {
                        'x': 25,
                        'y': 25,
                        'width': 200,
                        'height': 200,
                    },
                    'labels': [{
                        'name': 'box',
                        'probability': 0.45
                    }]
                }, {
                    'shape': {
                        'x': 75,
                        'y': 75,
                        'width': 150,
                        'height': 150,
                    },
                    'labels': [{
                        'name': 'box',
                        'probability': 0.05
                    }]
                }]
            }

    return Predictions()

class TestGetiDetectionInference:

    @pytest.mark.parametrize('threshold, expected', [(None, 0.0), (0.5, 0.5)])
    def test_init(self, threshold, expected):
        infer_obj = geti_inference.GetiDetectionInference(
            'path to deployment', 'CPU', threshold)
        assert infer_obj.threshold == expected

    @pytest.mark.parametrize('threshold, expected', [(None, 3), (0.0, 3),
                                                     (0.4, 2), (0.7, 1)])
    def test_process(self, frame, predictions, threshold, expected):
        infer_obj = geti_inference.GetiDetectionInference(
            'path to deployment', 'CPU', threshold)

        mocked_infer_obj = infer_obj.deployment.infer = MagicMock()
        mocked_infer_obj.return_value = predictions

        result = infer_obj.process(frame)
        assert result == True
        assert frame.add_region.call_count == expected
