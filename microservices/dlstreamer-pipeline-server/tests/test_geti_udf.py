#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import sys
import pytest
import numpy as np

from unittest.mock import MagicMock

sys.modules['geti_sdk.deployment'] = MagicMock()
sys.modules['geti_sdk.utils'] = MagicMock()
from udfs.python.geti_udf import geti_udf


@pytest.fixture
def frame():
    return np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)


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

        def overview(self):
            return Predictions.to_dict()

    return Predictions()

def test_get_default_prediction(frame):
    # Call the function
    prediction = geti_udf._get_default_prediction(frame)
    
    # Define the expected output
    expected_prediction = {
        'annotations': [{
            'labels': [{
                'probability': 1,
                'name': 'No object',
                'color': '#000000ff',
                'id': None,
                'source': None
            }],
            'shape': {
                'x': 0,
                'y': 0,
                'width': frame.shape[1],
                'height': frame.shape[0],
                'type': 'RECTANGLE'
            },
            'modified': None,
            'id': None,
            'labels_to_revisit': None
        }],
        'media_identifier': None,
        'id': None,
        'modified': None,
        'labels_to_revisit_full_scene': None,
        'annotation_state_per_task': None,
        'kind': 'prediction',
        'maps': [],
        'feature_vector': None,
        'created': None
    }
    
    # Assert that the output matches the expected output
    assert prediction == expected_prediction


class TestGetiUdf:

    @pytest.mark.parametrize('visualize, expected', [('True', 'True'),
                                                     ('False', 'False')])
    def test_init(self, visualize, expected):
        infer_obj = geti_udf.Udf('path to deployment', 'CPU', visualize)
        assert infer_obj.viz == expected

    @pytest.mark.parametrize('visualize', [('False'), ('True')])
    def test_process(self, mocker, frame, predictions, visualize):
        infer_obj = geti_udf.Udf('path to deployment', 'CPU', visualize)

        mocked_infer_obj = infer_obj.deployment.infer = MagicMock()
        mocked_infer_obj.return_value = predictions
        mock_pickle_dumps = mocker.patch('pickle.dumps', return_value=b'mocked_pickle')
        mock_codecs_encode = mocker.patch('codecs.encode', return_value=b'mocked_codecs')
        metadata = {'format': 'BGR'}
        drop_frame, output_frame, output_metadata = infer_obj.process(frame, metadata)
        assert drop_frame == False
        if visualize.upper() == 'TRUE':
            assert (sys.modules['geti_sdk.utils'].
                    show_image_with_annotation_scene).called
        else:
            assert np.array_equal(output_frame, frame)
       
        expected_metadata = {
            'task': 'object_detection',
            'predictions': predictions.to_dict()
        }
        assert output_metadata['task'] == expected_metadata['task']
        assert output_metadata['predictions'] == expected_metadata['predictions']