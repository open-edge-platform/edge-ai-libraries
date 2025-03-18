#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from src.server.pipeline import Pipeline
from unittest.mock import MagicMock

class TestPipeline:
    @pytest.fixture
    def sample_config(self):
        return {
            'pipelines': {
                'config': {
                    'key': 'value'
                }
            }
        }

    @pytest.fixture
    def sample_request(self):
        return {
            'req_section1': {
                'req_section2': {
                    'request_key': 'request_value'
                }
            }
        }

    def test_pipeline_state_stopped(self):
        assert Pipeline.State.QUEUED.stopped() is False
        assert Pipeline.State.RUNNING.stopped() is False
        assert Pipeline.State.COMPLETED.stopped() is True
        assert Pipeline.State.ERROR.stopped() is True
        assert Pipeline.State.ABORTED.stopped() is True
    
    @pytest.mark.parametrize(
    "config_section, result",
    [
        (['pipelines', 'config'], {'key': 'value'}),
        (['pipelines', 'config', 'key'], 'value'),
        (['pipelines', 'na'], {}),
        ([], {'pipelines': {'config': {'key': 'value'}}})
    ])
    def test_get_config_section(self,config_section,result,sample_config):
        assert Pipeline.get_config_section(sample_config, config_section)==result

    @pytest.mark.parametrize(
        "request_section, config_section, mock_config_result, req_result, config_result",
        [
            (['req_section1', 'req_section2'], ['pipelines', 'config'], {'mocked_key': 'mocked_value'}, {'request_key': 'request_value'}, {'mocked_key': 'mocked_value'}),
            (['req_section1', 'na'], ['pipelines', 'config'], {'mocked_key': 'mocked_value'}, {}, {'mocked_key': 'mocked_value'}),
            (['req_section1', 'na'], ['pipelines', 'na'], {}, {}, {})
        ]
    )
    def test_get_section_and_config(self, sample_request, sample_config, mocker, request_section, config_section, mock_config_result, req_result, config_result):
        mock_get_config_section = mocker.patch('src.server.pipeline.Pipeline.get_config_section', return_value=mock_config_result)
        req_result, config_result = Pipeline.get_section_and_config(sample_request, sample_config, request_section, config_section)
        mock_get_config_section.assert_called_once_with(sample_config, config_section)
        assert req_result == req_result
        assert config_result == mock_config_result