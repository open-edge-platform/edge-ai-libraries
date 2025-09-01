#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock
import src.common.log

from src.publisher.common.filter import Filter

src.common.log.configure_logging('DEBUG')

class TestUtils:

    @pytest.mark.parametrize('config, expected',
                             [({'type': 'classification','label_score': {'Person': 0.5 }}, True),
                              ({'type': 'detection','label_score': {'Person': 0.5 }}, True),
                              ({'type': 'segmentation'}, False),
                              (None, KeyError)])
    def test_check_filter_criteria(self, mocker, config, expected):
        mocker.patch('src.publisher.common.filter.Filter._check_detection_filter',return_value = True)
        mocker.patch('src.publisher.common.filter.Filter._check_classification_filter',return_value = True)
        
        try:
            filter_obj = Filter(config)
            filter = filter_obj.check_filter_criteria({})
            assert filter == expected
        except Exception as e:
            assert type(e) == expected


    @pytest.mark.parametrize('config, metadata, expected',
                             [({'type': 'classification','label_score': {'Person': 0.5 }},
                               {'classes': ['Vehicle'], 'Vehicle': 0.5}, True),
                              ({'type': 'classification','label_score': {'Person': 0.5 }},
                               {'classes': ['Person'], 'Person': 0.6}, True), 
                              ({'type': 'classification','label_score': {'Person': 0.5 }},
                               {'classes': ['Person'], 'Person': 0.3}, False), 
                              ({'type': 'classification','label_score': {'Person': 0.5 }},
                               {'classes': ['Person'], 'Person': 0.5}, True)])
    def test_check_classification_filter(self, mocker, config, metadata, expected):       
        filter_obj = Filter(config)
        filter = filter_obj._check_classification_filter(metadata)
        assert filter == expected


    @pytest.mark.parametrize('config, metadata, expected',
                             [({'type': 'detection','label_score': {'Person': 0.5 }},
                               {'predictions': {'annotations': [{'labels': [{'id': None, 'probability': 0.507821958065033, 'source': None, 'color': '#25a18eff', 'name': 'Person'}]}]}}, True),
                              ({'type': 'detection','label_score': {'Person': 0.5 }},
                               {'predictions': {'annotations': [{'labels': [{'id': None, 'probability': 0.507821958065033, 'source': None, 'color': '#25a18eff', 'name': 'Vehicle'}]}]}}, False),
                              ({'type': 'detection','label_score': {'Person': 0.7 }},
                               {'predictions': {'annotations': [{'labels': [{'id': None, 'probability': 0.527821958065033, 'source': None, 'color': '#25a18eff', 'name': 'Person'}]}]}}, False),
                              ({'type': 'detection','label_score': {'Person': 0.7, 'Vehicle': 0.3 }},
                               {'predictions': {'annotations': [{'labels': [{'id': None, 'probability': 0.527821958065033, 'source': None, 'color': '#25a18eff', 'name': 'Person'}]}]}}, False),
                              ({'type': 'detection','label_score': {'Person': 0.7}},
                               {'predictions': {'annotations': [{'labels': [{'id': None, 'probability': 0.527821958065033, 'source': None, 'color': '#25a18eff', 'name': 'Person'}]}]}}, False),
                              ({'type': 'detection','label_score': {'Person': 0.6}},
                               {'annotations': {'objects': [{'label': 'Person', 'score': 0.6827021241188049, 'bbox': [873, 484, 1045, 702], 'attributes': {'rotation': 0, 'occluded': 0}}]}}, True),
                              ({'type': 'detection','label_score': {'Person': 0.8}},
                               {'annotations': {'objects': [{'label': 'Person', 'score': 0.6827021241188049, 'bbox': [873, 484, 1045, 702], 'attributes': {'rotation': 0, 'occluded': 0}}]}}, False),
                              ({'type': 'detection','label_score': {'Person': 0.8}},
                               {}, False),

                            ])
    def test_check_detection_filter(self, mocker, config, metadata, expected):       
        filter_obj = Filter(config)
        filter = filter_obj._check_detection_filter(metadata)
        assert filter == expected
