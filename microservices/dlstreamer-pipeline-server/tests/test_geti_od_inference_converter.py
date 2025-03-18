#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
import logging
from unittest.mock import patch
from udfs.python.geti_udf.base_od_inference_converter import BaseODInferenceConverter
from udfs.python.geti_udf.geti_od_inference_converter import GetiODInferenceConverter

@pytest.fixture
def inference_result():
    return {
        'predictions': {
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
    }

@patch.object(BaseODInferenceConverter, 'convert_x1y1wh_to_x1y1x2y2', return_value=[[50, 50, 150, 150], [25, 25, 225, 225], [75, 75, 225, 225]])
def test_convert_inference_result(mock_convert, inference_result):
    converter = GetiODInferenceConverter()    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    log_capture = logging.StreamHandler()
    log_capture.setLevel(logging.DEBUG)
    logger.addHandler(log_capture)
    converted_result = converter.convert_inference_result(inference_result)
    expected_result = {
        'objects': [{
            'bbox': [50, 50, 150, 150],
            'label': 'box',
            'score': 0.75,
            'attributes': {
                'occluded': False,
                'rotation': 0.0
            }
        }, {
            'bbox': [25, 25, 225, 225],
            'label': 'box',
            'score': 0.45,
            'attributes': {
                'occluded': False,
                'rotation': 0.0
            }
        }, {
            'bbox': [75, 75, 225, 225],
            'label': 'box',
            'score': 0.05,
            'attributes': {
                'occluded': False,
                'rotation': 0.0
            }
        }]
    }
    
    assert converted_result == expected_result