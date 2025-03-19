# pylint: disable=import-error, redefined-outer-name, unused-argument
"""
This file provides functions for testing functions in the geti_manager.py file.
"""
# import pytest
# from managers.geti_manager import GetiManager, Geti, ProjectClient, ModelClient
# import models.project

# @pytest.fixture
# def mock_geti_clients(mocker):
#     """Return Geti clients"""
#     # Mock get_server_details_from_env function
#     mocker.patch("managers.geti_manager.get_server_details_from_env")
#     # Mock Geti Client
#     mock_geti_client = mocker.Mock(spec=Geti)
#     mocker.patch("managers.geti_manager.Geti", return_value=mock_geti_client)
#     # Add `session` and `workspace_id` attribute to mock_geti_client
#     mock_geti_client.session = None
#     mock_geti_client.workspace_id = ""

#     # Mock Project Client
#     mock_project_client = mocker.Mock(spec=ProjectClient)
#     mocker.patch("managers.geti_manager.ProjectClient", return_value=mock_project_client)

#     return {"geti_client": mock_geti_client, "project_client": mock_project_client}

# @pytest.mark.parametrize("g_projects_params", [
#     {"test_case": "no_projects", "identifier": None, "expected_result": []},
#     {"test_case": "existing_projects_no_active_models", "identifier": None, "expected_result": [
#         models.project.Project(id="project1", name="Test Project1", description="", created_date="", tasks=[], active_models=[]),
#         models.project.Project(id="project2", name="Test Project2", description="", created_date="", tasks=[], active_models=[])
#     ]},
#     {"test_case": "get_project_with_id_match_found", "identifier": "project1", "expected_result": [
#         models.project.Project(id="project1", name="Test Project1", description="", created_date="", tasks=[], active_models=[])
#     ]},
#     {"test_case": "get_project_with_id_no_match_found", "identifier": "project3", "expected_result": []},
# ])
# def test_get_projects(g_projects_params, mock_geti_clients, mocker):
#     """Test getting projects with various inputs """
#     # Mock Geti project_client get_all_projects method and set return value
#     mock_get_all_projects = mock_geti_clients["project_client"].get_all_projects
#     if g_projects_params["test_case"] == "no_projects":
#         mock_get_all_projects.return_value = []

#     elif g_projects_params["test_case"] in ["existing_projects_no_active_models", "get_project_with_id_match_found", "get_project_with_id_no_match_found"]:
#         mock_get_all_projects.return_value = [Project(id="project1", name="Test Project1",pipeline=Pipeline([Task("Detection", TaskType.DETECTION, [])], []), datasets=[]), Project(id="project2", name="Test Project2",pipeline=Pipeline([Task("Detection", TaskType.DETECTION, [])], []), datasets=[])]

#         # Mock geti_manager.get_data and set return value to []
#         mock_mlflow_manager = mocker.patch("managers.geti_manager.MLflowManager")
#         mock_mlflow_manager_get_models = mock_mlflow_manager.return_value.get_models
#         mock_mlflow_manager_get_models.return_value = []

#         # Mock Project Client
#         mock_model_client = mocker.Mock(spec=ModelClient)
#         mocker.patch("managers.geti_manager.ModelClient", return_value=mock_model_client)
#         mock_model_client.get_all_active_models.return_value = [Model(name="SSD ", fps_throughput="9", latency="30", precision=["FP16"], creation_date="2022-12-19 22:32:38.739000+00:00", architecture="SSD", score_up_to_date=False, optimization_capabilities=None, optimized_models=[OptimizedModel(name="ATSS OpenVINO FP32", fps_throughput="9", latency="20", precision=["FP16"], creation_date="2022-12-22 22:32:38.739000+00:00", id="12514asds654dsf", model_status="SUCCESS", optimization_methods=["openvino"], optimization_objectives={"":""}, optimization_type="ONNX")], id="132152sdfg")]

#     # Create GetiManager object and get projects
#     geti_manager = GetiManager()
#     geti_manager._geti_client = None # pylint: disable=protected-access
#     projects = geti_manager.get_projects(id_=g_projects_params["identifier"])

#     assert len(projects) == len(g_projects_params["expected_result"])

# @pytest.mark.parametrize("s_models_params", [
#     {"test_case": "no_projects", "project_id": "project1", "desired_model_ids": None, "expected_result": False},
#     # {"test_case": "existing_projects_no_active_models", "identifier": None, "expected_result": [
#     #     models.project.Project(id="project1", name="Test Project1", description="", created_date="", tasks=[], active_models=[], is_registered=False),
#     #     models.project.Project(id="project2", name="Test Project2", description="", created_date="", tasks=[], active_models=[], is_registered=False)
#     # ]},
#     # {"test_case": "get_project_with_id_match_found", "identifier": "project1", "expected_result": [
#     #     models.project.Project(id="project1", name="Test Project1", description="", created_date="", tasks=[], active_models=[], is_registered=False)
#     # ]},
#     # {"test_case": "get_project_with_id_no_match_found", "identifier": "project3", "expected_result": []},
# ])
# def test_save_models(s_models_params, mock_geti_clients, mocker):
#     """Test saving models with various inputs """
#     # Mock Geti project_client get_all_projects method and set return value
#     mock_get_all_projects = mock_geti_clients["project_client"].get_all_projects
#     if s_models_params["test_case"] == "no_projects":
#         mock_get_all_projects.return_value = []

#     # Create GetiManager object and get projects
#     geti_manager = GetiManager()
#     geti_manager._geti_client = None # pylint: disable=protected-access
#     model_ids_registered = geti_manager.save_models(project_id=s_models_params["project_id"])

#     assert model_ids_registered == s_models_params["expected_result"]
