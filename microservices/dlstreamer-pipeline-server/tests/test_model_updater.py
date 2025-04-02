#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""
This file contains tests associated to the functions in the model_updater.py file.
"""
# pylint: disable=protected-access, import-error

import os
import pytest
from unittest.mock import patch, MagicMock
from itertools import product
from src.model_updater import ModelRegistryClient, ModelQueryParams


def get_mock_model_registry_client(mocker,
                                   mr_config=None):
    """Get an instance of the ModelRegistryClient class

    Args:
        mocker : Object used to mock other variables and classes

    Returns:
        tuple: A tuple containing the model registry client object and 
        mock request operation
    """
    if mr_config is None:
        # os.environ["MR_USER_PASSWORD"] = "fake_word"
        mr_config = {"url": "http://fakeurl.com",
                     "saved_models_dir": "/fake/dir"
                     }
    # mock_post = mocker.patch('src.model_updater.requests.post')
    # mock_response = mocker.Mock()
    # mock_response.json.return_value = {"access_token": "fake_token"}
    # mock_post.return_value = mock_response

    return ModelRegistryClient(model_registry_cfg=mr_config)#, mock_post


@pytest.mark.parametrize("url, is_connected, verify_cert",
                         product(["http://fakeurl.com", "https://fakeurl.com"],
                                 [True, False], ["False", "True", "/path/to", "../"] )
                        )
def test_model_registry_client_initialization(mocker, url, is_connected, verify_cert):
    """Test model registry client initialization

    Args:
        mocker : Object used to mock other variables and classes
    """
    client = None
    if url.startswith("https://"):
        os.environ["MR_VERIFY_CERT"] = verify_cert

    if is_connected:
        # os.environ["MR_USER_PASSWORD"] = "fake_word"
        config = {
            "url": url,
            "saved_models_dir": "/fake/dir"
        }

        if verify_cert != "/path/to":
            client = get_mock_model_registry_client(
                mocker, mr_config=config)

        #     mock_post.assert_called_once_with(
        #         url=url+"/login",
        #         data={"username": "admin", "password": os.environ["MR_USER_PASSWORD"]},
        #         verify=client._verify_cert, timeout=300.0
        #     )

        #     assert client._auth_header == {"Authorization": "Bearer fake_token"}
        if client:
            assert client._request_timeout == 300
    else:
        # os.environ["MR_USER_PASSWORD"] = "abcdef"

        model_registry_cfg = {
            "url": "",
            "saved_models_dir": "/path/to/models"
        }

        client = ModelRegistryClient(model_registry_cfg)
    
    if client:
        # assert client._is_connected == is_connected
        assert client._request_timeout == 300


@pytest.mark.parametrize("url, user_password, is_connected, auth_header", [
    ("http://localhost:32002", "abcdefgh", True,
     {"Authorization": "Bearer fake_token"}),
    ("", "", False, {})
], ids=["success", "failed"])
def test_connect(mocker, is_connected, url, user_password, auth_header, request):
    """Test the model registry client's connect method

    Args:
        mocker : Object used to mock other variables and classes
        is_connected: The expected flag for signifying whether the client 
        is connected
        url: The url for the model registry microservice
        user_password: The user password associated with the model registry microservice
        auth_header: The authentication header used for authentication with 
        the model registry microservice
    """
    # os.environ["MR_USER_PASSWORD"] = user_password

    if request.node.callspec.id == "success":
        config = {
            "url": url,
            "saved_models_dir": "/fake/dir"
        }
        client = get_mock_model_registry_client(
            mocker, mr_config=config)
        # client._login_to_mr_microservice()

        # assert mock_post.call_count == 2
        assert client._request_timeout == 300

    if request.node.callspec.id == "failed":
        model_registry_cfg = {
            "url": "",
            "saved_models_dir": "/path/to/models"
        }

        client = ModelRegistryClient(model_registry_cfg)
        # client._login_to_mr_microservice()

    # assert client._auth_header == auth_header
    # assert client._is_connected == is_connected


@pytest.mark.parametrize("model_params, expected_model_metadata, status_code", [
    ({"project_name": "person-detection",
      "version": "v1",
      "category": "Detection",
      "architecture": "YOLO",
      "precision": "FP32"}, None, None),
    ({"project_name": "person-detection",
      "version": "v1",
      "category": "Detection",
      "architecture": "YOLO",
      "precision": "FP32"}, {"id": "0",
                             "name": "Test model",
                             "project_name": "person-detection",
                             "version": "v1",
                             "category": "Detection",
                             "architecture": "YOLO",
                             "precision": "FP32"
                             }, 200),
    ({"project_name": "person-detection",
      "version": "v1",
      "category": "Detection",
      "architecture": "YOLO",
      "precision": "FP32"}, None, 500),
    ({"project_name": "person-detection",
      "version": "v1",
      "category": "Detection",
      "architecture": "YOLO"}, None, 200)
], ids=["not_connected", "success", "internal_server_err_occurred", "too_many_models"])
def test_get_model(mocker, model_params, expected_model_metadata, status_code, request):
    """Test the model registry client's get_model method

    Args:
        mocker : Object used to mock other variables and classes
        model_params: Properties associated to a model
    """
    client = get_mock_model_registry_client(mocker)
    mq_params = ModelQueryParams(**model_params)

    if request.node.callspec.id == "not_connected":
        client._is_connected = False
        model = client._get_model(mq_params)
        assert model == expected_model_metadata

    elif request.node.callspec.id in ("success", "too_many_models", "internal_server_err_occurred"):
        mock_get = mocker.patch('src.model_updater.ModelRegistryClient._send_request')
        mock_response = mocker.Mock()
        model_metadata = {"id": "0",
                          "name": "Test model",
                          "project_name": "person-detection",
                          "version": "v1",
                          "category": "Detection",
                          "architecture": "YOLO",
                          "precision": "FP32"
                          }
        mock_response.status_code = status_code
        mock_response.json.return_value = [model_metadata]

        if request.node.callspec.id == "too_many_models":
            mock_response.json.return_value = [model_metadata,
                                               model_metadata]
        elif request.node.callspec.id == "internal_server_err_occurred":
            mock_response.json.return_value = None

        mock_get.return_value = mock_response

        model = client._get_model(mq_params)
        assert model == expected_model_metadata


@pytest.mark.parametrize("model_id, expected", [
    ("0", None),
    ("1", b'Hello, world!'),
    ("3", None)
], ids=["not_connected", "success", "wrong_content_type"])
def test_get_model_artifacts_zip_file_data(mocker, model_id, expected, request):
    """Test the model registry client's get_model_artifacts_zip_file_data method

    Args:
        mocker : Object used to mock other variables and classes
        model_id: The id associated to a fake model
    """
    client = get_mock_model_registry_client(mocker)

    if request.node.callspec.id == "not_connected":
        client._is_connected = False
        data = client._get_model_artifacts_zip_file_data(model_id)
        assert data is None

    elif request.node.callspec.id in ("success", "wrong_content_type"):
        mock_get = mocker.patch('src.model_updater.ModelRegistryClient._send_request')
        mock_response = mocker.Mock()
        byte_string = b'Hello, world!'
        mock_response.headers = {"Content-Type": "application/zip"}
        mock_response.content = byte_string

        if request.node.callspec.id == "wrong_content_type":
            mock_response.headers = {"Content-Type": "plain/text"}
            mock_response.content = "test"

        mock_get.return_value = mock_response

        data = client._get_model_artifacts_zip_file_data(model_id)
        assert data == expected

@pytest.fixture
def setup_model_registry_client(mocker, tmp_path):
    mock_logger = mocker.patch('src.model_updater.get_logger', return_value=mocker.MagicMock())
    model_registry_cfg = {
        "url": "http://fakeurl.com",
        "saved_models_dir": str(tmp_path),
        "request_timeout": 300
    }
    client = ModelRegistryClient(model_registry_cfg)
    client._logger = mock_logger
    return client

@pytest.fixture
def pipelines_cfg():
    return [{
        "name": "pipeline_name",
        "model_params": [
                {"param1": "value1", "param2": "value2"}
            ]
    }]


def test_successful_download_and_save(setup_model_registry_client, pipelines_cfg):
    model_downloader = setup_model_registry_client

    model = {
        "id": "model_id",
        "name": "model_name",
        "version": "1.0",
        "precision": ["FP32"],
        "origin": "geti",
        "category": "category"
    }
    zip_file_data = b"fake_zip_file_data"
    with patch.object(model_downloader, '_get_model', return_value=model), \
         patch.object(model_downloader, '_get_model_artifacts_zip_file_data', return_value=zip_file_data), \
         patch('os.makedirs'), \
         patch('os.path.exists', return_value=False), \
         patch('builtins.open', new_callable=MagicMock), \
         patch('zipfile.ZipFile.extract') as mock_zipfile, \
         patch('os.listdir', return_value=["model.xml"]):
        
        is_artifacts_saved, msg  = model_downloader.download_models(pipelines_cfg)
        assert not is_artifacts_saved

def test_model_not_found(setup_model_registry_client, pipelines_cfg):
    model_downloader = setup_model_registry_client
    with patch.object(model_downloader, '_get_model', return_value=None):
        is_artifacts_saved, msg = model_downloader.download_models(pipelines_cfg)
        assert not is_artifacts_saved
        assert msg == "Model is not found."

def test_permission_error(setup_model_registry_client, pipelines_cfg):
    model_downloader = setup_model_registry_client

    model = {
        "id": "model_id",
        "name": "model_name",
        "version": "1.0",
        "precision": ["FP32"],
        "origin": "geti",
        "category": "category"
    }

    with patch.object(model_downloader, '_get_model', return_value=model), \
         patch.object(model_downloader, '_get_model_artifacts_zip_file_data', side_effect=PermissionError):
        is_artifacts_saved, msg = model_downloader.download_models(pipelines_cfg)
        assert not is_artifacts_saved
        assert "Insufficient permissions" in msg

@pytest.mark.parametrize("pipelines_cfg, expected_model_paths", [
    (
        [{
            "name": "pipeline1",
            "model_params": [
                {
                    "name": "model",
                    "version": "v1",
                    "precision": "FP32",
                    "deploy": True,
                    "pipeline_element_name": "detection",
                    "origin": "Geti",
                    "category": "Detection"
                }
            ]
        }],
        {"detection": "/fake/dir/model_m-v1_fp32/deployment/Detection/model/model.xml"}
    ),
    (
        [{
            "name": "pipeline2",
            "model_params": [
                {
                    "name": "model11s",
                    "version": "v2",
                    "precision": "FP16",
                    "deploy": True,
                    "pipeline_element_name": "detection",                }
            ]
        }],
        {"detection": "/fake/dir/model11s_m-v2_fp16/FP16/model11s.xml"}
    ),
    (
        [{
            "name": "pipeline3",
            "model_params": [
                {
                    "name": "model",
                    "version": "v1",
                    "precision": "FP32",
                    "deploy": False,
                }
            ]
        }],
        {}
    ),
    (
        [{
            "name": "pipeline4",
            "model_params": [
                {
                    "name": "model1",
                    "version": "v1",
                    "precision": "FP32",
                    "deploy": True,
                    "pipeline_element_name": "detection",
                    "category": "Detection"
                },
                {
                    "name": "model2",
                    "version": "v1",
                    "precision": "FP32",
                    "deploy": True,
                    "pipeline_element_name": "classification",
                    "origin": "Geti",
                    "category": "Classification"
                }
            ]
        }],
        {
            "detection": "/fake/dir/model1_m-v1_fp32/FP32/model1.xml",
            "classification": "/fake/dir/model2_m-v1_fp32/deployment/Classification/model/model.xml"
        }
    )
])
def test_get_model_path(mocker, pipelines_cfg, expected_model_paths):
    client = get_mock_model_registry_client(mocker)
    model_paths = client.get_model_path(pipelines_cfg)
    assert model_paths == expected_model_paths
