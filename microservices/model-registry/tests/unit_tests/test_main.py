# pylint: disable=import-error, unused-argument
"""
This file provides functions for testing functions in the main.py file.
"""
import io
import pytest
from fastapi.testclient import TestClient
from fastapi import Response
from main import app
# from models.project import ProjectOut, ActiveModel
from models.registered_model import RegisteredModel

client = TestClient(app)

def test_health_check():
    """Test health check"""
    response = client.get("/health")
    assert response.status_code == 200

def test_health_check_status_and_body():
    """Test health check endpoint returns correct status and body."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_get_registered_models(mocker):
    """Test Scenario: Get registered models"""
    expected_num_registered_models = 2
    def mock_get_models(self, keys=None, values=None):
        return [RegisteredModel(id="4545d456fs1d3g456",
                                name="SSD FP32 OpenVINO",
                                target_device="CPU",
                                created_date="2022-12-19 22:32:38.739000+00:00",
                                last_updated_date="2023-11-23 03:25:56.303000",
                                precision=["FP32"],
                                size=1210000,
                                version="13",
                                format="openvino",
                                origin="Geti",
                                file_url="minio://model_registry/63a0e686c30715f28a829f68/deployment.zip",
                                project_id="1321d23f1gfd13"),
                RegisteredModel(id="4545d456fs1d3g456sd",
                                name="SSD FP16 OpenVINO",
                                target_device="CPU",
                                created_date="2022-12-19 22:32:38.739000+00:00",
                                last_updated_date="2023-11-23 03:25:56.303000",
                                precision=["FP32"],
                                size=1210000,
                                version="13",
                                format="openvino",
                                origin="Geti",
                                file_url="minio://model_registry/63a0e686c30715f28a829f68/deployment.zip",
                                project_id="1321d23f1ghkj7gfd13")]

    mocker.patch(
        'main.MLflowManager.get_models', mock_get_models,
    )

    response = client.get("/models")
    assert response.status_code == 200
    assert len(response.json()) == expected_num_registered_models

def test_get_models_empty(mocker):
    """Test /models returns 200 and empty list if no models and no query params."""
    mocker.patch('main.MLflowManager.get_models', return_value=[])
    response = client.get("/models")
    assert response.status_code == 200
    assert response.json() == []

def test_get_registered_model_invalid_q_params(mocker):
    """Test Scenario: Get registered models with invalid query string parameters"""
    response = client.get("/models?format=FP32")
    assert response.status_code == 422

def test_get_models_not_found_with_query(mocker):
    """Test /models returns 404 if no models and query params present."""
    mocker.patch('main.MLflowManager.get_models', return_value=[])
    response = client.get("/models?name=foo")
    assert response.status_code == 404
    assert b"Model(s) not found." in response.content

def test_get_registered_model_valid_id(mocker):
    """Test Scenario: Get registered models"""
    expected_model_id = "4545d456fs1d3g456sd"
    def mock_get_models(self, model_id = None):
        return [RegisteredModel(id="4545d456fs1d3g456sd",
                                name="SSD FP16 OpenVINO",
                                target_device="CPU",
                                created_date="2022-12-19 22:32:38.739000+00:00",
                                last_updated_date="2023-11-23 03:25:56.303000",
                                precision=["FP32"],
                                size=1210000,
                                version="13",
                                format="openvino",
                                origin="Geti",
                                file_url="minio://model_registry/63a0e686c30715f28a829f68/deployment.zip",
                                project_id="1321d23f1ghkj7gfd13")]

    mocker.patch(
        'main.MLflowManager.get_models', mock_get_models,
    )

    response = client.get("/models/4545d456fs1d3g456sd")
    assert response.status_code == 200
    assert response.json()["id"] == expected_model_id

def test_get_model_by_id_not_found(mocker):
    """Test /models/{model_id} returns 400 if model model id is not in the correct format."""
    mocker.patch('main.MLflowManager.get_models', return_value=[])
    response = client.get("/models/doesnotexist")
    assert response.status_code == 400
    assert b'{"detail":"Invalid format for model ID."}' in response.content

def test_get_model_by_id_found(mocker):
    """Test /models/{model_id} returns model if found."""
    from models.registered_model import RegisteredModel
    model = RegisteredModel(id="12a42512a42512a425", name="Test", target_device="CPU", created_date="2020", last_updated_date="2020", precision=["FP32"], size=1, version="1", format="openvino", origin="Geti", file_url="minio://bucket/file.zip", project_id="pid")
    mocker.patch('main.MLflowManager.get_models', return_value=[model])
    response = client.get("/models/12a42512a42512a425")
    assert response.status_code == 200
    assert response.json()["id"] == "12a42512a42512a425"

def test_get_zip_for_registered_model_valid_id(mocker):
    """Test Scenario: Get zip file for registered model with valid id"""

    def mock_get_registered_model_by_id(model_id = None):
        return RegisteredModel(id="4545d456fs1d3g456sd",
                                name="SSD FP16 OpenVINO",
                                target_device="CPU",
                                created_date="2022-12-19 22:32:38.739000+00:00",
                                last_updated_date="2023-11-23 03:25:56.303000",
                                precision="FP32",
                                size=1210000,
                                version="13",
                                format="openvino",
                                origin="Geti",
                                file_url="minio://model_registry/63a0e686c30715f28a829f68/deployment.zip",
                                project_id="1321d23f1ghkj7gfd13")

    def mock_get_object(self, object_name=None):
        return b"ahfhareyh45y5wyen5y65y46wy55w54w56b54w"

    mocker.patch(
        'main.MinioManager.get_object', mock_get_object,
    )

    mocker.patch(
        'main.get_registered_model_by_id', mock_get_registered_model_by_id,
    )

    response = client.get("/models/4545d456fs1d3g456sd/files")
    assert response.status_code == 200
    content_type = response.headers['Content-Type']
    media_type = content_type.split(';')[0]
    assert media_type == 'application/zip'

def test_get_zip_for_registered_model_by_id_success(mocker):
    """Test /models/{model_id}/files returns 200 and correct content type."""
    from models.registered_model import RegisteredModel
    model = RegisteredModel(id="4545d456fs1d3g456see", name="Test", target_device="CPU", created_date="2020", last_updated_date="2020", precision=["FP32"], size=1, version="1", format="openvino", origin="Geti", file_url="minio://bucket/file.zip", project_id="pid")
    mocker.patch('main.get_registered_model_by_id', return_value=model)
    mocker.patch('main.MinioManager.get_object', return_value=b"zipbytes")
    response = client.get("/models/4545d456fs1d3g456see/files")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/zip")

def test_get_zip_for_registered_model_invalid_id(mocker):
    """Test Scenario: Get zip file for registered model with invalid id"""

    def mock_get_models(self, model_id = None):
        return []

    mocker.patch(
        'main.MLflowManager.get_models', mock_get_models,
    )

    def mock_get_object(self, object_name=None):
        return b"ahfhareyh45y5wyen5y65y46wy55w54w56b54w"

    mocker.patch(
        'main.MinioManager.get_object', mock_get_object,
    )

    response = client.get("/models/4545d456fs1d3g456sd/files")
    assert response.status_code == 404
    assert b"Model not found." in response.content

def test_get_zip_for_registered_model_by_id_not_found(mocker):
    """Test /models/{model_id}/files returns 404 if model not found."""
    mocker.patch('main.get_registered_model_by_id', return_value=Response("Model not found.\n", status_code=404))
    response = client.get("/models/4545d456fs1d3g456seen/files")
    assert response.status_code == 404
    assert b"Model not found." in response.content

def test_get_zip_for_registered_model_exception_raised(mocker):
    """Test Scenario: Get zip file for registered model with exception raised"""

    def mock_get_models(self, model_id = None):
        raise ValueError("")

    mocker.patch(
        'main.MLflowManager.get_models', mock_get_models,
    )

    response = client.get("/models/4545d456fs1d3g456sd/files")
    assert response.status_code == 500

def test_main_file_execution(mocker):
    """Test Scenario: Get zip file for registered model with exception raised"""

    def mock_get_models(self, model_id = None):
        raise ValueError("")

    mocker.patch(
        'main.MLflowManager.get_models', mock_get_models,
    )

    response = client.get("/models/4545d456fs1d3g456sd/files")
    assert response.status_code == 500

@pytest.mark.parametrize("s_model_params", [
    {"test_case": "unsupported_key", "form_data": {"name": "ATSS_Test", "target_device": "CPU", "precision": "fp32", "version": "1", "format": "openvino", "score": "0.50", "accuracy":""},  "expected_status_code": 422, "expected_result": "Unsupported key(s) found: accuracy"},
    {"test_case": "unsupported_file_type", "form_data": {"name": "ATSS_Test", "target_device": "CPU", "precision": "fp32", "version": "1", "format": "openvino", "score": "0.50"},  "expected_status_code": 422, "expected_result": "Unsupported file type found: text/plain"},
    {"test_case": "model_id_already_exists", "form_data": {"id":"4545d456fs1d3g456", "name": "ATSS_Test", "target_device": "CPU", "precision": "fp32", "version": "1", "format": "openvino", "score": "0.50"},  "expected_status_code": 409, "expected_result": "The requested action could not be completed due to a conflict with model '4545d456fs1d3g456'."},
    {"test_case": "successful_model_registration", "form_data": {"name": "ATSS_Test", "target_device": "CPU", "precision": "fp32", "version": "1", "format": "openvino", "score": "0.50"},  "expected_status_code": 201, "expected_result": "1"},
])
def test_store_model(s_model_params, mocker):
    """Test Scenarios: Store model"""
    file = None
    file_data = b"This is a file"
    upload_file = io.BytesIO(file_data)
    upload_file.seek(0)  # Rewind the buffer
    if s_model_params["test_case"] == "unsupported_file_type":
        file = ("test.txt", upload_file)
    else:
        file = ("test.zip", upload_file)

    if s_model_params["test_case"] == "successful_model_registration":
        def mock_get_no_model(self):
            return []

        mocker.patch(
            'main.MLflowManager.get_models', mock_get_no_model,
        )

        def mock_register_model(self, metadata, file_content, file_name):
            return "1", False, ""

        mocker.patch(
            'main.MLflowManager.register_model', mock_register_model,
        )

    if s_model_params["test_case"] == "model_id_already_exists":
        def mock_get_models(self, keys=None, values=None):
            return [RegisteredModel(id="4545d456fs1d3g456",
                                    name="SSD FP32 OpenVINO",
                                    target_device="CPU",
                                    created_date="2022-12-19 22:32:38.739000+00:00",
                                    last_updated_date="2023-11-23 03:25:56.303000",
                                    precision=["FP32"],
                                    size=1210000,
                                    version="13",
                                    format="openvino",
                                    origin="Geti",
                                    file_url="minio://model_registry/63a0e686c30715f28a829f68/deployment.zip",
                                    project_id="1321d23f1gfd13"),
                    RegisteredModel(id="4545d456fs1d3g456sd",
                                    name="SSD FP16 OpenVINO",
                                    target_device="CPU",
                                    created_date="2022-12-19 22:32:38.739000+00:00",
                                    last_updated_date="2023-11-23 03:25:56.303000",
                                    precision=["FP32"],
                                    size=1210000,
                                    version="13",
                                    format="openvino",
                                    origin="Geti",
                                    file_url="minio://model_registry/63a0e686c30715f28a829f68/deployment.zip",
                                    project_id="1321d23f1ghkj7gfd13")]

        mocker.patch(
            'main.MLflowManager.get_models', mock_get_models,
        )

    response = client.post("/models",
                           data=s_model_params["form_data"],
                           files={"file": file})

    assert response.status_code == s_model_params["expected_status_code"]
    assert s_model_params["expected_result"] in response.text

def test_delete_registered_model_valid_id(mocker):
    """Test Scenario: Delete registered model with valid id"""

    def mock_delete_models(self, m_id = None):
        return True

    mocker.patch(
        'main.MLflowManager.delete_model', mock_delete_models,
    )

    response = client.delete("/models/4545d456fs1d3g456sd")
    assert response.status_code == 204
    assert response.content == b""

def test_delete_model_success(mocker):
    """Test /models/{model_id} DELETE returns 204 for successful delete."""
    mocker.patch('main.MLflowManager.delete_model', return_value=True)
    response = client.delete("/models/4545d456fs1d3g456seeing")
    assert response.status_code == 204

def test_delete_registered_model_invalid_id(mocker):
    """Test Scenario: Delete registered model with invalid id"""

    def mock_delete_models(self, m_id = None):
        return False

    mocker.patch(
        'main.MLflowManager.delete_model', mock_delete_models,
    )

    response = client.delete("/models/4545d456fs1d3g456sd")
    assert response.status_code == 404
    assert b"Model not found." in response.content

def test_delete_model_not_found(mocker):
    """Test /models/{model_id} DELETE returns 404 if model not found."""
    mocker.patch('main.MLflowManager.delete_model', return_value=False)
    response = client.delete("/models/4545d456fs1d3g456sees")
    assert response.status_code == 404
    assert b"Model not found." in response.content

def test_update_model_valid_data(mocker):
    """Test Scenario: Update model with valid data"""
    model_id = "4545d456fs1d3g456sd"
    update_data = {
        "name": "Updated Model Name",
        "version": "2"
    }

    def mock_get_registered_model_by_id(model_id):
        return RegisteredModel(id=model_id,
                                name="SSD FP16 OpenVINO",
                                target_device="CPU",
                                created_date="2022-12-19 22:32:38.739000+00:00",
                                last_updated_date="2023-11-23 03:25:56.303000",
                                precision="FP32",
                                size=1210000,
                                version="13",
                                format="openvino",
                                origin="Geti",
                                file_url="minio://model_registry/63a0e686c30715f28a829f68/deployment.zip",
                                project_id="1321d23f1ghkj7gfd13")

    def mock_update_model(self, model_id, metadata):
        return True, False, ""

    mocker.patch('main.get_registered_model_by_id', mock_get_registered_model_by_id)
    mocker.patch('main.MLflowManager.update_model', mock_update_model)

    response = client.put(f"/models/{model_id}", data=update_data)
    assert response.status_code == 200
    assert response.json() == {"status": "completed"}

def test_update_model_empty(mocker):
    """Test /models/{model_id} PUT returns 400 for empty update."""
    response = client.put("/models/abc", json={})
    assert response.status_code == 400

def test_update_model_invalid_data(mocker):
    """Test Scenario: Update model with invalid data"""
    model_id = "4545d456fs1d3g456sd"
    update_data = {
        "unsupported_field": "value"
    }

    response = client.put(f"/models/{model_id}", json=update_data)
    assert response.status_code == 400
    assert response.json() == {
        "status": "error",
        "message": "Invalid request. Check the request body and ensure at least 1 supported field is provided."
    }

def test_update_model_not_found(mocker):
    """Test Scenario: Update model that does not exist"""
    model_id = "nonexistent_model_id"
    update_data = {
        "name": "Updated Model Name"
    }

    def mock_get_registered_model_by_id(model_id):
        return Response("Model not found.\n", status_code=404)

    mocker.patch('main.get_registered_model_by_id', mock_get_registered_model_by_id)

    response = client.put(f"/models/{model_id}", data=update_data)
    assert response.status_code == 404
    assert response.content == b"Model not found.\n"

def test_update_model_conflict(mocker):
    """Test Scenario: Update model with conflict (duplicate model)"""
    model_id = "4545d456fs1d3g456sd"
    update_data = {
        "name": "Updated Model Name"
    }

    def mock_get_registered_model_by_id(model_id):
        return RegisteredModel(id=model_id,
                                name="SSD FP16 OpenVINO",
                                target_device="CPU",
                                created_date="2022-12-19 22:32:38.739000+00:00",
                                last_updated_date="2023-11-23 03:25:56.303000",
                                precision="FP32",
                                size=1210000,
                                version="13",
                                format="openvino",
                                origin="Geti",
                                file_url="minio://model_registry/63a0e686c30715f28a829f68/deployment.zip",
                                project_id="1321d23f1ghkj7gfd13")

    def mock_update_model(self, model_id, metadata):
        return False, True, "Model ID conflict"

    mocker.patch('main.get_registered_model_by_id', mock_get_registered_model_by_id)
    mocker.patch('main.MLflowManager.update_model', mock_update_model)

    response = client.put(f"/models/{model_id}", data=update_data)
    assert response.status_code == 409
    assert response.content == b"The requested action could not be completed due to a conflict with model Model ID conflict"
