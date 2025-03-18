#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest import mock
from unittest.mock import patch, MagicMock
from collections import defaultdict
from src.server.model_manager import ModelManager,ModelsDict

@pytest.fixture
def model_manager(mocker):
    mock_models = mocker.MagicMock()
    mock_models.return_value = {'model1': {'v1': {'networks' : {'custom': {'description': 'model1', 'labels': 'models/model1/v1/labels.txt', 'network': 'models/model1/v1/model.xml', 'proc': 'models/model1/v1/model-proc.json', 'type': 'IntelDLDT'}}}}}
    mocker.patch.object(ModelManager,'load_models',return_value=True)
    model_dir = "models"
    model_manager_instance = ModelManager(model_dir, ignore_init_errors=True)
    model_manager_instance.models = mock_models.return_value
    return model_manager_instance

@pytest.fixture
def model_manager_for_load_models(mocker):
    model_dir = "models"
    return ModelManager(model_dir, ignore_init_errors=True)

class TestModelManager:
   
    def isdir_side_effect(self, path):
        directories = ["path/custom","path"]
        return path in directories

    @pytest.mark.parametrize(
    "version, result",
    [
        ('1', 1),
        (1, 1),
        ('not_a_number', 'not_a_number'),
        (None, None)
    ])
    def test_convert_version(self, model_manager, version, result):
        assert model_manager.convert_version(version) == result

    @pytest.mark.parametrize(
        "mocked_listdir, path, model_property, extension, expected_result, expected_exception",
        [
            (['model-proc.json', 'abc.xml', 'labels.txt'], 'path', 'model-proc', 'json', 'path/model-proc.json', None),
            (['model-proc.json', 'abc.xml', 'labels.txt'], 'path', 'label', 'txt', 'path/labels.txt', None),
            ([], 'path', 'label', 'txt', None, None),
            (['model-proc.json', 'model-proc.json'], 'path', 'model-proc', 'json', None, "Multiple model-proc files found in path"),
        ]
    )
    def test_get_model_property(self, mocked_listdir, path, model_property, extension, expected_result, expected_exception, model_manager, mocker):
        mocker.patch('os.listdir', return_value=mocked_listdir)
        mocker.patch('os.path.abspath', side_effect=lambda x: x)
        if expected_exception:
            with pytest.raises(Exception) as exp:
                model_manager._get_model_property(path, model_property, extension)
            assert str(exp.value) == expected_exception
        else:
            result = model_manager._get_model_property(path, model_property, extension)
            assert result == expected_result

    @pytest.mark.parametrize(
        "mocked_listdir, path, expected_result, expected_exception",
        [
            (['model.xml'], 'path', 'path/model.xml', None),
            (['model.xml', 'network.blob'], 'path', None, 'Multiple networks found in path'),
            ([], 'path', None, None),
        ]
    )
    def test_get_model_network(self,mocked_listdir, path, expected_result, expected_exception, model_manager, mocker):
        mocker.patch('os.listdir', return_value=mocked_listdir)
        mocker.patch('os.path.abspath', side_effect=lambda x: x)
        if expected_exception:
            with pytest.raises(Exception) as excinfo:
                model_manager._get_model_network(path)
            assert str(excinfo.value) == expected_exception
        else:
            result = model_manager._get_model_network(path)
            assert result == expected_result

    @pytest.mark.parametrize(
        "mocked_listdir, expected_result",
        [
            (['model.xml', 'model-proc.json','custom'], {'default': 'path/model.xml', 'custom': {'network': 'path/custom/net.xml'}}),
            (['model.xml', 'model-proc.json'], {'default': 'path/model.xml'})
        ]
    )
    def test_get_model_networks(self, model_manager, mocker,mocked_listdir, expected_result):
        mocker.patch('src.server.model_manager.ModelManager._get_model_network', side_effect=['path/model.xml','path/custom/net.xml'])
        mocker.patch('os.listdir', return_value=mocked_listdir)
        mocker.patch('os.path.isdir', side_effect=self.isdir_side_effect)
        result = model_manager._get_model_networks('path')
        assert result == expected_result

    def test_load_models(self, model_manager_for_load_models, mocker):
        mocker.patch('os.path.abspath', side_effect=lambda x: x)
        mocker.patch('os.path.isdir', side_effect=lambda x: x in ['models', 'models/model1', 'models/model1/v1'])
        mocker.patch('os.listdir', side_effect=lambda x: {
            'models': ['model1'],
            'models/model1': ['v1'],
            'models/model1/1': ['model.xml', 'model-proc.json', 'labels.txt']
        }[x])
        mocker.patch('src.server.model_manager.ModelManager.convert_version', side_effect=lambda x: x)
        mocker.patch('src.server.model_manager.ModelManager._get_model_property', side_effect=lambda path, prop, ext: f'{path}/{prop}.{ext}')
        mocker.patch('src.server.model_manager.ModelManager._get_model_networks', return_value={'custom': { 'network' : 'models/model1/v1/model.xml'}})
        success = model_manager_for_load_models.load_models('models', None)
        assert success
        assert 'model1' in model_manager_for_load_models.models
        assert 'v1' in model_manager_for_load_models.models['model1']
        assert model_manager_for_load_models.model_properties["model-proc"]['models/model1/v1/model.xml'] == 'models/model1/v1/model-proc.json'
        assert model_manager_for_load_models.model_properties["labels"]['models/model1/v1/model.xml'] == 'models/model1/v1/labels.txt'
        model_dict = model_manager_for_load_models.models['model1']['v1']
        assert model_dict['networks']['custom']['network'] == 'models/model1/v1/model.xml'
        assert model_dict['networks']['custom']['proc'] == 'models/model1/v1/model-proc.json'
        assert model_dict['networks']['custom']['labels'] == 'models/model1/v1/labels.txt'
        assert model_dict['networks']['custom']['version'] == 'v1'
        assert model_dict['networks']['custom']['type'] == 'IntelDLDT'
        assert model_dict['networks']['custom']['description'] == 'model1'

    def test_get_model_parameters(self, model_manager, mocker):
        model_manager.models['model1']['v1']['description'] = "model_description"
        model_manager.models['model1']['v1']['type'] = "model_type"
        params = model_manager.get_model_parameters("model1", 'v1')
        assert params is not None
        assert params["name"] == "model1"
        assert params["version"] == 'v1'
        assert "networks" in params
        assert "model-proc" in params["networks"]
        assert "labels" in params["networks"]
        assert "type" in params["type"]
        assert "description" in params["description"]
        params_na = model_manager.get_model_parameters("model2", 'v1')
        assert params_na is None
    
    def test_get_loaded_models(self, model_manager, mocker):
        loaded_models = model_manager.get_loaded_models()
        assert len(loaded_models) == 1
        assert loaded_models[0]["name"] == "model1"
        assert loaded_models[0]["version"] == "v1"

    def test_get_default_network_for_device(self,model_manager,mocker):
        mock_model = "model[VA_DEVICE_DEFAULT]"
        device = "AUTO GPU"
        mock_ret = MagicMock()
        mock_get_network = mocker.patch.object(model_manager,'get_network',return_value = mock_ret)
        result = model_manager.get_default_network_for_device(device,mock_model)
        assert result == mock_ret
        mock_get_network.assert_called_once_with(mock_model,"FP16")
        mocker.patch.object(model_manager,'get_network',return_value = None)
        result = model_manager.get_default_network_for_device(device,mock_model)
        assert result == "model"
        result = model_manager.get_default_network_for_device("GPU2",mock_model)
        assert result == "model"

    def test_get_network(self,model_manager):
        mock_model = "{models}[VA_DEVICE_DEFAULT]"
        network = "FP16"
        result = model_manager.get_network(mock_model,network)
        assert result == "{'model1': {'v1': {'networks': {'custom': {'description': 'model1', 'labels': 'models/model1/v1/labels.txt', 'network': 'models/model1/v1/model.xml', 'proc': 'models/model1/v1/model-proc.json', 'type': 'IntelDLDT'}}}}}[FP16]"
        result = model_manager.get_network("{models['temp']}[VA_DEVICE_DEFAULT]",network)
        assert result is None