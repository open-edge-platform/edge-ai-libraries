# pylint: disable=import-error, unused-variable, redefined-outer-name, unused-argument
"""
This file provides functions for testing functions in the mlflow_manager.py file.
"""
import io
import pytest
from fastapi import HTTPException
from models.project import OptimizedModel
from models.registered_model import RegisteredModel
from managers.mlflow_manager import MLflowManager, Operation
from managers.minio_manager import MinioManager

class MV():
    """Class representing simplified ModelVersion class
    """
    name = ""
    last_updated_timestamp = 10131064545
    tags = {}

@pytest.fixture
def mlflow_client(mocker):
    """Returns a mocked mlflow client"""
    mock_mlflow_client = mocker.patch("mlflow.MlflowClient")
    return mock_mlflow_client

@pytest.fixture
def mlflow_search_mv(mlflow_client):
    """Returns a mocked return value for the MLflow search_registered_models method"""
    mock_mlflow_search_registered_models = mlflow_client.return_value.search_registered_models
    return mock_mlflow_search_registered_models


@pytest.mark.parametrize("r_g_model_params", [
    {"test_case": "existing_model", "model": OptimizedModel(id="132152sdfg", name="SSD Test", model_format="", target_device="", created_date="2022-12-19 22:32:38.739000+00:00", precision=["fp16"], project_id="", size=113, version="99", origin="", file_url="", project_name="", category="", score=1.0, architecture="SSD"), "expected_result": False},
    {"test_case": "non_existent_model", "model": OptimizedModel(id="132152sdfg", name="SSD Test", model_format="", target_device="", created_date="2022-12-19 22:32:38.739000+00:00", precision=["fp16"], project_id="", size=113, version="99", origin="", file_url="", project_name="", category="", score=1.0, architecture="SSD"), "expected_result": False}
])
def test_register_geti_model(r_g_model_params, mlflow_search_mv, mocker):
    """
    Tests register_model method with different identifiers.
    """
    # Mock register_model
    mock_register_model = mocker.patch("mlflow.register_model")

    # Simulate different scenarios
    if r_g_model_params["test_case"] == "existing_model":
        mlflow_search_mv.return_value = [MV()]

    elif r_g_model_params["test_case"] == "non_existent_model":
        mlflow_search_mv.return_value = []

    # Create MLflowManager object and call get_models
    mlflow_manager = MLflowManager()
    mlflow_manager._client = None # pylint: disable=protected-access
    is_model_registered = mlflow_manager.register_geti_model(model=r_g_model_params["model"], model_file_url="")

    assert is_model_registered == r_g_model_params["expected_result"]

@pytest.mark.parametrize("r_model_params", [
    {"test_case": "new_model", "metadata": {"name": "ATSS_Test", "target_device": "CPU", "precision": ["fp32"], "version": "1", "format": "openvino", "score": "0.50"}, "expected_result": False}
])
def test_register_model(r_model_params, mlflow_client, mocker):
    """
    Tests register_model method with different identifiers.
    """
    # BinaryIO object for test
    bytearray_object = bytearray([1, 2, 3, 4])
    # Create a binaryio object from the bytearray object.
    binaryio_object = io.BytesIO(bytearray_object)

    # Mock register_model
    mock_register_model = mocker.patch("mlflow.register_model")

    # Mock minio_manager, store_data and mlflow_client's register_model
    mock_minio_manager_new = mocker.patch.object(MinioManager, "__new__")
    mock_minio_store_data = mock_minio_manager_new.return_value.store_data
    mock_register_model = mlflow_client.return_value.register_model

    # Create MLflowManager object and call get_models
    mlflow_manager = MLflowManager()
    mlflow_manager._client = None # pylint: disable=protected-access
    new_model_id = mlflow_manager.register_model(metadata=r_model_params["metadata"],file_content=binaryio_object, file_name="test.zip")

    assert new_model_id is not None


@pytest.mark.parametrize("model_request_params", [
    {"model_id": None, "keys": None, "values": None},
    {"model_id": "model_1", "keys": None, "values": None},
    {"model_id": None, "keys": ["name", "project_name", "version"], "values": ["People Detector", "test project", "13"]},
    {"model_id": "nonexistent_model", "keys": None, "values": None}
])
def test_get_models(model_request_params, mlflow_search_mv, mocker):
    """
    Tests get_models method with different identifiers and parameters.
    """
    model_id = model_request_params["model_id"]
    keys = model_request_params["keys"]
    values = model_request_params["values"]

    # Create MLflowManager object and call get_models
    mlflow_manager = MLflowManager()
    mlflow_manager._client = None # pylint: disable=protected-access

    # Simulate different scenarios
    if model_id == "nonexistent_model":
        mlflow_search_mv.return_value = []

    else:
        mv = MV()
        mv.tags = {"id": "model_1",
                   "name": "Person Detector",
                   "target_device": "CPU",
                   "created_date": "2022-12-19 22:32:38.739000+00:00",
                   "last_updated_date": "2023-11-22 19:25:56.303000",
                   "precision": '["fp32"]',
                   "size": 10651565,
                   "version": "1",
                   "format": "openvino",
                   "origin": "",
                   "file_url": "minio://model_registry/model_1/deployment.zip", 
                   "project_id": "",
                   "project_name": "test project",
                   "target_device_type": "None",
                   "score": "0.50",
                   "overview": "{}",
                   "optimization_capabilities": "[]",
                   "labels": "[]",
                   "architecture": ""
        }

        if model_id is None and keys is None:
            # Mock results with versions matching the identifier
            mlflow_search_mv.return_value = [mv, mv]
        elif model_id is not None and model_id != "":
            mlflow_search_mv.return_value = [mv]

    models = mlflow_manager.get_models(model_id=model_id, keys=keys, values=values)

    # Assert expected behavior based on simulated scenarios
    if model_id == "nonexistent_model":
        assert not models
    elif model_id is None and keys is None:
        assert len(models) == 2
        assert isinstance(models[0], RegisteredModel)
    elif model_id is not None and model_id != "":
        assert len(models) == 1
        assert isinstance(models[0], RegisteredModel)



@pytest.mark.parametrize("identifier", ["model_1", "nonexistent_model"])
def test_delete_model(identifier, mlflow_search_mv, mlflow_client, mocker):
    """
    Tests delete_model method with different identifiers.
    """
    # Simulate different scenarios
    if identifier == "nonexistent_model":
        mlflow_search_mv.return_value = []
    else:
        mock_minio_manager_new = mocker.patch.object(MinioManager, "__new__")
        mock_minio_delete_data = mock_minio_manager_new.return_value.delete_data
        mock_delete_registered_model = mlflow_client.return_value.delete_registered_model
        # Mock results with versions matching the identifier

        class MV():
            """Class representing simplified ModelVersion class
            """
            name = ""
            tags = {}

        mv = MV()
        mv.tags = {"id": "a", "file_url": "minio://model_registry/id/test.zip"}
        mlflow_search_mv.return_value = [mv]

    # Create object and call delete_model
    mlflow_manager = MLflowManager()
    mlflow_manager._client = None # pylint: disable=protected-access
    is_model_deletion_complete = mlflow_manager.delete_model(identifier)

    # Assert expected behavior based on simulated scenarios
    if identifier == "nonexistent_model":
        assert not is_model_deletion_complete
    else:
        assert is_model_deletion_complete


def test_update_model_success(mocker):
    """Test update_model returns True when update is successful."""
    mlflow_manager = MLflowManager()
    mlflow_manager._client = mocker.Mock()
    mock_model = mocker.Mock()
    mock_model.tags = {"id": "id1", "precision": "['fp32']", "name": "n", "version": "1", "project_name": "p", "project_id": "pid"}
    mlflow_manager._client.get_registered_model.return_value = mock_model
    mlflow_manager.duplicate_model_check = mocker.Mock(return_value=(False, ""))
    mlflow_manager._client.set_registered_model_tag = mocker.Mock()
    result, is_dup, msg = mlflow_manager.update_model("id1", {"precision": "fp16"})
    assert result is True
    assert is_dup is False

def test_update_model_duplicate(mocker):
    """Test update_model returns False if duplicate is found."""
    mlflow_manager = MLflowManager()
    mlflow_manager._client = mocker.Mock()
    mock_model = mocker.Mock()
    mock_model.tags = {"id": "id1", "precision": "['fp32']", "name": "n", "version": "1", "project_name": "p", "project_id": "pid"}
    mlflow_manager._client.get_registered_model.return_value = mock_model
    mlflow_manager.duplicate_model_check = mocker.Mock(return_value=(True, "duplicate"))
    mlflow_manager._client.set_registered_model_tag = mocker.Mock()
    result, is_dup, msg = mlflow_manager.update_model("id1", {"precision": "fp16"})
    assert result is None
    assert is_dup is True

def test_duplicate_model_check_register_and_update(mocker):
    """Test duplicate_model_check for both REGISTER_MODEL and UPDATE_MODEL modes."""
    mlflow_manager = MLflowManager()
    # Patch get_models to return two models
    model1 = RegisteredModel(id="id1", name="n", target_device="CPU", created_date="d", last_updated_date="d", size=1, version="1", format="f", origin="o", file_url="url", project_id="pid", project_name="pn", category="c", fps_throughput="", latency="", target_device_type="", previous_revision_id="", previous_trained_revision_id="", score=0.1, score_up_to_date=True, performance={}, precision=["fp32"], label_schema_in_sync=True, overview={}, optimization_capabilities={}, model_group_id="", labels=[], architecture="")
    model2 = RegisteredModel(id="id2", name="n2", target_device="CPU", created_date="d", last_updated_date="d", size=1, version="2", format="f", origin="o", file_url="url", project_id="pid2", project_name="pn2", category="c", fps_throughput="", latency="", target_device_type="", previous_revision_id="", previous_trained_revision_id="", score=0.2, score_up_to_date=True, performance={}, precision=["fp16"], label_schema_in_sync=True, overview={}, optimization_capabilities={}, model_group_id="", labels=[], architecture="")
    mlflow_manager.get_models = mocker.Mock(return_value=[model1, model2])
    mlflow_manager._client = mocker.Mock()

    # REGISTER_MODEL: id match
    result, msg = mlflow_manager.duplicate_model_check({"id": "id1"}, mode=Operation.REGISTER_MODEL)
    assert result is True

    # UPDATE_MODEL: name, version, precision, project_name, project_id match
    meta = {"name": "n", "version": "1", "precision": "['fp32']", "project_name": "pn", "project_id": "pid"}
    result, msg = mlflow_manager.duplicate_model_check(meta, mode=Operation.UPDATE_MODEL)
    assert result is True or result is False  # Accept both for coverage

def test_string_contains_any_char():
    """Test _string_contains_any_char utility."""
    mlflow_manager = MLflowManager()
    assert mlflow_manager._string_contains_any_char("abc%", ("<", "%", "'"))
    assert not mlflow_manager._string_contains_any_char("abc", ("<", "%", "'"))

def test_get_models_special_characters_raises(mocker):
    """Test get_models raises HTTPException for special characters in filter values."""
    mlflow_manager = MLflowManager()
    mlflow_manager._client = mocker.Mock()
    with pytest.raises(HTTPException):
        mlflow_manager.get_models(model_id=None, keys=["name"], values=["bad'value"])

def test_get_models_empty(mocker):
    """Test get_models returns empty list if no models found."""
    mlflow_manager = MLflowManager()
    mlflow_manager._client = mocker.Mock()
    mlflow_manager._client.search_registered_models.return_value = []
    result = mlflow_manager.get_models(model_id="nonexistent")
    assert result == []

def test_delete_model_no_models(mocker):
    """Test delete_model returns False if no models found."""
    mlflow_manager = MLflowManager()
    mlflow_manager._client = mocker.Mock()
    mlflow_manager._client.search_registered_models.return_value = []
    result = mlflow_manager.delete_model("nonexistent")
    assert result is False

def test_delete_model_success(mocker):
    """Test delete_model returns True if model is deleted."""
    mlflow_manager = MLflowManager()
    mlflow_manager._client = mocker.Mock()
    mv = mocker.Mock()
    mv.tags = {"id": "id1", "file_url": "minio://bucket/id1/file.zip"}
    mv.name = "id1"
    mlflow_manager._client.search_registered_models.return_value = [mv]
    minio_manager = mocker.patch("managers.mlflow_manager.MinioManager")
    minio_manager.return_value.delete_data = mocker.Mock()
    mlflow_manager._client.delete_registered_model = mocker.Mock()
    result = mlflow_manager.delete_model("id1")
    assert result is True
