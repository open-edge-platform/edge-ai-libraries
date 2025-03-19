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


# def test_get_projects_valid(mocker):
#     """Test Scenario: Get Geti projects"""
#     expected = [
#         Project("1", "Project #1", "Test Test", "", [], []),
#         Project("1", "Project #2", "Test Test", "", [], [])
#     ]

#     def mock_get_projects(self):
#         return [Project("1", "Project #1", "Test Test", "", [], []), Project("1", "Project #2", "Test Test", "", [], [])]

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects
#     )

#     response = client.get("/projects")
#     # Check that the response's status code is 200
#     assert response.status_code == 200
#     # Check that the response contains the expected number of Geti projects
#     assert len(response.json()) == len(expected)


# def test_get_projects_connection_error(mocker):
#     """Test Scenario: Get Geti projects with UnboundLocalError raised"""

#     def mock_get_projects(self):
#         raise UnboundLocalError("")

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects
#     )

#     response = client.get("/projects")
#     assert response.status_code == 500
#     assert b"ConnectionError" in response.content


# def test_get_projects_value_error(mocker):
#     """Test Scenario: Get Geti projects with ValueError raised"""

#     def mock_get_projects(self):
#         raise ValueError("")

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects
#     )

#     response = client.get("/projects")
#     assert response.status_code == 500
#     assert b"ValueError" in response.content


# def test_get_project_valid_id(mocker):
#     """Test Scenario: Get project with valid id"""
#     expected = Project("1", "Project #1", "Test Test", "", [], [])

#     def mock_get_project(self, id_=None):
#         return [Project("1", "Project #1", "Test Test", "", [], []),
#                 Project("2", "Project #2", "Test Test", "", [], [])]

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_project
#     )

#     response = client.get("/projects/1")
#     # Check that the response's status code is 200
#     assert response.status_code == 200
#     # Check that the response contains the expected number of Geti projects
#     project_json = response.json()
#     assert project_json["id"] == expected.id


# def test_get_project_invalid_id(mocker):
#     """Test Scenario: Get project using invalid id"""
#     # Check the case when no models found

#     def mock_get_project(self, id_=None):
#         return []

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_project
#     )
#     response = client.get("/projects/0")
#     # Check that the response's status code is 404
#     assert response.status_code == 404


# def test_get_project_connection_error(mocker):
#     """Test Scenario: Get project with UnboundLocalError raised"""

#     def mock_get_projects(self, id_=None):
#         raise UnboundLocalError("")

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects
#     )
#     response = client.get("/projects/2")
#     # Check that the response's status code is 404
#     assert response.status_code == 500
#     assert b"ConnectionError" in response.content


# def test_get_project_value_error(mocker):
#     """Test Scenario: Get project with UnboundLocalError raised"""
#     # Check the case when an exception is raised

#     def mock_get_projects(self, id_=None):
#         raise ValueError("")

#     mocker.patch(
#         # get_projects method associated to the GetiManager class is located in the src/managers/geti_manager.py file, but imported to main.py
#         'main.GetiManager.get_projects', mock_get_projects
#     )
#     response = client.get("/projects/3")
#     # Check that the response's status code is 404
#     assert response.status_code == 500
#     assert b"ValueError" in response.content


# def test_save_project_and_models_valid_ids(mocker):
#     """Test Scenario: Save project and model(s) with valid ids"""
#     expected_saved_model_id = "637bceae87a2ca49b30c362a"

#     def mock_get_projects(self, id_=None):
#         return [Project(id="3", name="Project #3", description="Test Test", created_date="", tasks=[], active_models=[ActiveModel(id="637bceae87a2ca49b30c362a", name="SSD FP32 OpenVINO", is_registered=False)])]

#     def mock_save_models(self, project_id=None,
#                          desired_model_ids=None):
#         return ["637bceae87a2ca49b30c362a"]

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects,
#     )
#     mocker.patch(
#         'main.GetiManager.save_models', mock_save_models,
#     )

#     req_body = {
#         "active_model_ids": ["637bceae87a2ca49b30c362a"]
#     }
#     response = client.post("/projects/3/geti-models/download", json=req_body)

#     assert response.status_code == 201
#     successful_text = f'Model(s): {expected_saved_model_id} registered.'
#     assert successful_text.encode("utf-8") in response.content


# def test_save_project_and_models_invalid_ids(mocker):
#     """Test Scenario: Save project and model(s) with invalid ids"""

#     def mock_get_projects(self, id_=None):
#         return [Project(id="3", name="Project #3", description="Test Test", created_date="", tasks=[], active_models=[ActiveModel(id="637bceae87a2ca49b30c362a", name="SSD FP32 OpenVINO", is_registered=False)])]

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects,
#     )

#     req_body = {
#         "active_model_ids": ["637bceae87a2ca49b30c6655"]
#     }
#     response = client.post("/projects/3/geti-models/download", json=req_body)

#     assert response.status_code == 404
#     assert b"Project or model id not found." in response.content


# def test_save_project_and_models(mocker):
#     """Test Scenario: Save project and all model(s)"""

#     expected_saved_model_ids = [
#         "637bceae87a2ca49b30c362a", "637bceae87a2ca49b30c362b"]

#     def mock_get_projects(self, id_=None):
#         return [Project(id="3", name="Project #3", description="Test Test", created_date="", tasks=[], active_models=[ActiveModel(id="637bceae87a2ca49b30c362a", name="SSD FP32 OpenVINO", is_registered=False), ActiveModel(id="637bceae87a2ca49b30c362b", name="SSD FP16 OpenVINO", is_registered=False)])]

#     def mock_save_models(self, project_id=None,
#                          desired_model_ids=None):
#         return ["637bceae87a2ca49b30c362a", "637bceae87a2ca49b30c362b"]

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects,
#     )
#     mocker.patch(
#         'main.GetiManager.save_models', mock_save_models,
#     )

#     req_body = None
#     response = client.post("/projects/3/geti-models/download", json=req_body)

#     assert response.status_code == 201
#     successful_text = f'Model(s): {", ".join(expected_saved_model_ids)} registered.'
#     assert successful_text.encode("utf-8") in response.content


# def test_save_project_and_models_already_registered(mocker):
#     """Test Scenario: Save project and model(s) including some already registered"""

#     expected_registered_model_id = "637bceae87a2ca49b30c362a"

#     def mock_get_projects(self, id_=None):
#         return [Project(id="3", name="Project #3", description="Test Test", created_date="", tasks=[], active_models=[ActiveModel(id="637bceae87a2ca49b30c362a", name="SSD FP32 OpenVINO", is_registered=True), ActiveModel(id="637bceae87a2ca49b30c362b", name="SSD FP16 OpenVINO", is_registered=False)])]

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects,
#     )

#     req_body = None
#     response = client.post("/projects/3/geti-models/download", json=req_body)

#     assert response.status_code == 409
#     successful_text = f'Model(s): {expected_registered_model_id} is already registered.'
#     assert successful_text.encode("utf-8") in response.content


# def test_save_project_and_models_exception(mocker):
#     """Test Scenario: Save project and model(s) with exception raised"""

#     def mock_get_projects(self, id_=None):
#         return [Project(id="3", name="Project #3", description="Test Test", created_date="", tasks=[], active_models=[ActiveModel(id="637bceae87a2ca49b30c362a", name="SSD FP32 OpenVINO", is_registered=False), ActiveModel(id="637bceae87a2ca49b30c362b", name="SSD FP16 OpenVINO", is_registered=False)])]

#     def mock_save_models(self, project_id=None,
#                          desired_model_ids=None):
#         raise ValueError("")

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects,
#     )
#     mocker.patch(
#         'main.GetiManager.save_models', mock_save_models,
#     )

#     req_body = None
#     response = client.post("/projects/3/geti-models/download", json=req_body)

#     assert response.status_code == 500


# def test_save_project_and_models_no_registration(mocker):
#     """Test Scenario: Save project and model(s) as a result no models are registered"""

#     def mock_get_projects(self, id_=None):
#         return [Project(id="3", name="Project #3", description="Test Test", created_date="", tasks=[], active_models=[ActiveModel(id="637bceae87a2ca49b30c362a", name="SSD FP32 OpenVINO", is_registered=False), ActiveModel(id="637bceae87a2ca49b30c362b", name="SSD FP16 OpenVINO", is_registered=False), ActiveModel(id="637bceae87a2ca49b30c362c", name="SSD FP16 ONNX", is_registered=False)])]

#     def mock_save_models(self, project_id=None,
#                          desired_model_ids=None):
#         return None

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects,
#     )
#     mocker.patch(
#         'main.GetiManager.save_models', mock_save_models,
#     )

#     req_body = req_body = {
#         "active_model_ids": ["637bceae87a2ca49b30c362a"]
#     }
#     response = client.post("/projects/3/geti-models/download", json=req_body)

#     assert response.status_code == 500


# def test_save_project_and_models_non_openvino_model(mocker):
#     """Test Scenario: Save project and model(s) as a result no models are registered"""

#     def mock_get_projects(self, id_=None):
#         return [Project(id="3", name="Project #3", description="Test Test", created_date="", tasks=[], active_models=[ActiveModel(id="637bceae87a2ca49b30c362a", name="SSD FP32 OpenVINO", is_registered=False), ActiveModel(id="637bceae87a2ca49b30c362b", name="SSD FP16 OpenVINO", is_registered=False), ActiveModel(id="637bceae87a2ca49b30c362c", name="SSD FP16 ONNX", is_registered=False)])]

#     def mock_save_models(self, project_id=None,
#                          desired_model_ids=None):
#         return []

#     mocker.patch(
#         'main.GetiManager.get_projects', mock_get_projects,
#     )
#     mocker.patch(
#         'main.GetiManager.save_models', mock_save_models,
#     )

#     req_body = req_body = {
#         "active_model_ids": ["637bceae87a2ca49b30c362c"]
#     }
#     response = client.post("/projects/3/geti-models/download", json=req_body)

#     assert response.status_code == 403


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

def test_get_registered_model_invalid_q_params(mocker):
    """Test Scenario: Get registered models with invalid query string parameters"""
    response = client.get("/models?format=FP32")
    assert response.status_code == 422

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

def test_get_registered_model_invalid_id(mocker):
    """Test Scenario: Get registered models"""
    def mock_get_models(self, model_id = None):
        return []

    mocker.patch(
        'main.MLflowManager.get_models', mock_get_models,
    )

    response = client.get("/models/i7978n5t343e121r")
    assert response.status_code == 404
    assert b"Model not found" in response.content

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

def test_update_model_no_data(mocker):
    """Test Scenario: Update model with no data provided"""
    model_id = "4545d456fs1d3g456sd"
    update_data = {}

    response = client.put(f"/models/{model_id}", json=update_data)
    assert response.status_code == 400
    assert response.json() == {
        "status": "error",
        "message": "Invalid request. Check the request body and ensure at least 1 supported field is provided."
    }

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
