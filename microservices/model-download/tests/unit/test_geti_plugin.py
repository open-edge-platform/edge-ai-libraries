# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Test script to verify model retrieval and download methods work with the reference implementation pattern.
"""
import asyncio
import os
import sys
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from pathlib import Path

# Ensure the repository's src directory is on the path
ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from plugins.geti_plugin import GetiPlugin


def _mock_task(task_id, task_type):
    task = Mock()
    task.id = task_id
    task.task_type = task_type
    return task


async def test_get_model_group():
    """Test that get_model_group properly retrieves models from ModelClient"""
    print("Test 1: get_model_group()")
    print("-" * 50)
    
    # Create mock SDK objects
    mock_model_group = Mock()
    mock_model_group.id = "group1"
    mock_model_group.name = "Detection Model"
    
    mock_model1 = Mock()
    mock_model1.id = "model1"
    mock_model1.name = "Base Model"
    mock_model1.model_group_id = "group1"
    
    mock_model2 = Mock()
    mock_model2.id = "model2"
    mock_model2.name = "Optimized Model"
    mock_model2.model_group_id = "group1"
    
    mock_project = Mock()
    mock_project.id = "proj1"
    mock_project.name = "Test Project"
    
    # Create plugin instance
    with patch.dict(os.environ, {
        'GETI_HOST': 'test-host',
        'GETI_TOKEN': 'test-token',
        'GETI_WORKSPACE': 'test-ws',
        'GETI_ORGANIZATION': 'test-org'
    }):
        plugin = GetiPlugin()
        
        # Mock SDK objects
        plugin.geti = Mock()
        plugin.geti.workspace_id = "ws123"
        plugin.geti.session = Mock()
        
        with patch.object(plugin, 'get_projects', new_callable=AsyncMock) as mock_get_projects:
            mock_get_projects.return_value = [{"project": mock_project}]
            
            with patch('plugins.geti_plugin.ModelClient') as mock_model_client_class:
                mock_model_client = Mock()
                mock_model_client.get_all_model_groups = Mock(return_value=[mock_model_group])
                mock_model_client.get_latest_model_for_all_model_groups = Mock(return_value=[mock_model1, mock_model2])
                mock_model_client_class.return_value = mock_model_client
                
                with patch('plugins.geti_plugin.asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
                    async def to_thread_side_effect(func, *args):
                        return func(*args)
                    mock_thread.side_effect = to_thread_side_effect
                    
                    result = await plugin.get_model_group("proj1", "group1")
                    
                    print(f"✓ Result type: {type(result)}")
                    print(f"✓ Result keys: {result.keys() if result else 'None'}")
                    if result:
                        print(f"✓ Model group ID: {result.get('id')}")
                        print(f"✓ Model group name: {result.get('name')}")
                        print(f"✓ Models count: {len(result.get('models', []))}")
                        print(f"✓ Models: {[(m.get('name'), m.get('id')) for m in result.get('models', [])]}")
                        assert result['id'] == 'group1'
                        assert len(result['models']) == 2
                        print("✓ PASSED\n")
                    else:
                        print("✗ FAILED - Result is None\n")
                        return False
    return True


async def test_get_model_id_by_name():
    """Test that get_model_id_by_name properly searches models"""
    print("Test 2: get_model_id_by_name()")
    print("-" * 50)
    
    mock_model_group = Mock()
    mock_model_group.id = "group1"
    mock_model_group.name = "Detection Model"
    
    mock_model1 = Mock()
    mock_model1.id = "model1"
    mock_model1.name = "Base Model"
    mock_model1.model_group_id = "group1"
    
    mock_model2 = Mock()
    mock_model2.id = "model2"
    mock_model2.name = "Optimized Model"
    mock_model2.model_group_id = "group1"
    
    mock_project = Mock()
    mock_project.id = "proj1"
    mock_project.name = "Test Project"
    
    with patch.dict(os.environ, {
        'GETI_HOST': 'test-host',
        'GETI_TOKEN': 'test-token',
        'GETI_WORKSPACE': 'test-ws',
        'GETI_ORGANIZATION': 'test-org'
    }):
        plugin = GetiPlugin()
        
        plugin.geti = Mock()
        plugin.geti.workspace_id = "ws123"
        plugin.geti.session = Mock()
        
        with patch.object(plugin, 'get_model_group', new_callable=AsyncMock) as mock_get_group:
            mock_get_group.return_value = {
                "id": "group1",
                "name": "Detection Model",
                "models": [
                    {"id": "model1", "name": "Base Model"},
                    {"id": "model2", "name": "Optimized Model"}
                ]
            }
            
            # Test finding existing model
            result = await plugin.get_model_id_by_name("proj1", "group1", "Base Model")
            print(f"✓ Found model 'Base Model': {result}")
            assert result == "model1"
            
            # Test finding another model
            result = await plugin.get_model_id_by_name("proj1", "group1", "Optimized Model")
            print(f"✓ Found model 'Optimized Model': {result}")
            assert result == "model2"
            
            # Test model not found
            result = await plugin.get_model_id_by_name("proj1", "group1", "Non-existent Model")
            print(f"✓ Model 'Non-existent Model' not found (as expected): {result}")
            assert result is None
            
            print("✓ PASSED\n")
    return True


async def test_download_model_from_geti():
    """Test that download_model_from_geti uses the correct SDK pattern"""
    print("Test 3: download_model_from_geti()")
    print("-" * 50)
    
    mock_base_model = Mock()
    mock_base_model.id = "model1"
    mock_base_model.name = "Base Model"
    mock_base_model.model_group_id = "group1"
    mock_base_model.optimized_models = []
    
    mock_optimized = Mock()
    mock_optimized.id = "opt1"
    mock_optimized.name = "Optimized"
    
    mock_model_with_optimized = Mock()
    mock_model_with_optimized.id = "model1"
    mock_model_with_optimized.name = "Base Model"
    mock_model_with_optimized.model_group_id = "group1"
    mock_model_with_optimized.optimized_models = [mock_optimized]
    
    mock_project = Mock()
    mock_project.id = "proj1"
    mock_project.name = "Test Project"
    
    with patch.dict(os.environ, {
        'GETI_HOST': 'test-host',
        'GETI_TOKEN': 'test-token',
        'GETI_WORKSPACE': 'test-ws',
        'GETI_ORGANIZATION': 'test-org'
    }):
        plugin = GetiPlugin()
        plugin.geti = Mock()
        plugin.geti.workspace_id = "ws123"
        plugin.geti.session = Mock()

        plugin._ensure_initialized = AsyncMock()
        plugin._get_project = AsyncMock(return_value=mock_project)
        mock_model_client = Mock()
        mock_model_client._get_model_detail = Mock(return_value=mock_base_model)
        mock_model_client._download_model = Mock()
        plugin._get_or_create_model_client = AsyncMock(return_value=mock_model_client)
        plugin.extract_model_files = AsyncMock()
        
        with patch('plugins.geti_plugin.asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
            async def to_thread_side_effect(func, *args, **kwargs):
                return func(*args, **kwargs)
            mock_thread.side_effect = to_thread_side_effect
            
            with patch('os.makedirs'), \
                 patch('os.path.exists', return_value=False), \
                 patch('os.path.join', side_effect=lambda *args: '/'.join(args)):
                
                model_path, error, ignored = await plugin.download_model_from_geti(
                    model_id="model1",
                    output_dir="/tmp/models",
                    model_name="Base Model",
                    export_type="base",
                    project_id="proj1",
                    model_group_id="group1"
                )
                
                print(f"✓ Download returned path: {model_path}")
                print(f"✓ Errors: {error}, Ignored fields: {ignored}")
                plugin._ensure_initialized.assert_awaited_once()
                plugin._get_project.assert_awaited_once_with("proj1")
                plugin._get_or_create_model_client.assert_awaited_once_with("proj1", mock_project)
                mock_model_client._get_model_detail.assert_called_once_with("group1", "model1")
                mock_model_client._download_model.assert_called_once()
                plugin.extract_model_files.assert_awaited_once()
                assert error is None
                assert ignored is None
                print("✓ PASSED\n")
    return True


async def test_list_models_filters_and_paginates():
    """Test that list_models returns Geti models with basic filters and pagination."""
    print("Test 4: list_models()")
    print("-" * 50)

    mock_project = Mock()
    mock_project.id = "proj1"
    mock_project.name = "Detection Project"
    mock_project.get_trainable_tasks.return_value = [_mock_task("task1", "detection")]

    mock_group = Mock()
    mock_group.id = "group1"
    mock_group.name = "Detector Group"
    mock_group.task_id = "task1"

    mock_optimized_fp16 = Mock()
    mock_optimized_fp16.id = "opt-fp16"
    mock_optimized_fp16.model_format = "OpenVINO"
    mock_optimized_fp16.precision = ["FP16"]

    mock_optimized_int8 = Mock()
    mock_optimized_int8.id = "opt-int8"
    mock_optimized_int8.model_format = "OpenVINO"
    mock_optimized_int8.precision = ["INT8"]

    mock_model = Mock()
    mock_model.id = "model1"
    mock_model.name = "Vehicle Detector"
    mock_model.model_group_id = "group1"
    mock_model.optimized_models = [mock_optimized_fp16, mock_optimized_int8]

    with patch.dict(os.environ, {
        'GETI_HOST': 'test-host',
        'GETI_TOKEN': 'test-token',
        'GETI_WORKSPACE_ID': 'ws123'
    }):
        plugin = GetiPlugin()
        plugin.geti = Mock()
        plugin.geti.workspace_id = "ws123"
        plugin.geti.session = Mock()

        plugin._ensure_initialized = AsyncMock()
        plugin.get_projects = AsyncMock(return_value=[{
            "id": "proj1",
            "name": "Detection Project",
            "project": mock_project,
        }])

        mock_model_client = Mock()
        mock_model_client.get_all_model_groups = Mock(return_value=[mock_group])
        mock_model_client.get_latest_model_for_all_model_groups = Mock(return_value=[mock_model])
        plugin._get_or_create_model_client = AsyncMock(return_value=mock_model_client)

        with patch('plugins.geti_plugin.asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
            async def to_thread_side_effect(func, *args, **kwargs):
                return func(*args, **kwargs)
            mock_thread.side_effect = to_thread_side_effect

            result = await plugin._list_models_async(
                filters={
                    "project_id": "proj1",
                    "project_name": "Detection",
                    "model_group_id": "group1",
                    "model_name": "vehicle",
                    "precision": "FP16",
                    "model_format": "OpenVINO",
                },
                limit=1,
                offset=0,
            )

            print(f"✓ Total models: {result['total']}")
            print(f"✓ Items: {result['items']}")
            assert result["total"] == 1
            assert len(result["items"]) == 1
            item = result["items"][0]
            assert item["name"] == "Vehicle Detector"
            assert item["owner"] == "Detection Project"
            assert item["precisions"] == ["FP16"]
            assert item["model_type"] == "detection"
            assert item["metadata"]["workspace_id"] == "ws123"
            assert item["metadata"]["project_id"] == "proj1"
            assert item["metadata"]["model_group_id"] == "group1"
            assert item["metadata"]["optimized_model_ids"] == ["opt-fp16"]
            assert "ignored_filter_fields" not in item["metadata"]
            print("✓ PASSED\n")
    return True


async def test_list_models_lists_workspace_models_without_project_scope():
    """Test that Geti listing can discover models across projects in a workspace."""
    print("Test 5: list_models() workspace discovery")
    print("-" * 50)

    mock_project1 = Mock()
    mock_project1.id = "proj1"
    mock_project1.name = "Detection Project"
    mock_project1.get_trainable_tasks.return_value = [_mock_task("task1", "detection")]

    mock_project2 = Mock()
    mock_project2.id = "proj2"
    mock_project2.name = "Classification Project"
    mock_project2.get_trainable_tasks.return_value = [_mock_task("task2", "classification")]

    mock_group1 = Mock()
    mock_group1.id = "group1"
    mock_group1.name = "Detector Group"
    mock_group1.task_id = "task1"

    mock_group2 = Mock()
    mock_group2.id = "group2"
    mock_group2.name = "Classifier Group"
    mock_group2.task_id = "task2"

    mock_optimized1 = Mock()
    mock_optimized1.id = "opt1"
    mock_optimized1.model_format = "OpenVINO"
    mock_optimized1.precision = ["FP16"]

    mock_optimized2 = Mock()
    mock_optimized2.id = "opt2"
    mock_optimized2.model_format = "OpenVINO"
    mock_optimized2.precision = ["INT8"]

    mock_model1 = Mock()
    mock_model1.id = "model1"
    mock_model1.name = "Vehicle Detector"
    mock_model1.model_group_id = "group1"
    mock_model1.optimized_models = [mock_optimized1]

    mock_model2 = Mock()
    mock_model2.id = "model2"
    mock_model2.name = "Product Classifier"
    mock_model2.model_group_id = "group2"
    mock_model2.optimized_models = [mock_optimized2]

    with patch.dict(os.environ, {
        'GETI_HOST': 'test-host',
        'GETI_TOKEN': 'test-token',
        'GETI_WORKSPACE_ID': 'ws123'
    }):
        plugin = GetiPlugin()
        plugin.geti = Mock()
        plugin.geti.workspace_id = "ws123"
        plugin.geti.session = Mock()

        plugin._ensure_initialized = AsyncMock()
        plugin.get_projects = AsyncMock(return_value=[
            {"id": "proj1", "name": "Detection Project", "project": mock_project1},
            {"id": "proj2", "name": "Classification Project", "project": mock_project2},
        ])

        mock_model_client1 = Mock()
        mock_model_client1.get_all_model_groups = Mock(return_value=[mock_group1])
        mock_model_client1.get_latest_model_for_all_model_groups = Mock(return_value=[mock_model1])

        mock_model_client2 = Mock()
        mock_model_client2.get_all_model_groups = Mock(return_value=[mock_group2])
        mock_model_client2.get_latest_model_for_all_model_groups = Mock(return_value=[mock_model2])

        plugin._get_or_create_model_client = AsyncMock(side_effect=[mock_model_client1, mock_model_client2])

        with patch('plugins.geti_plugin.asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
            async def to_thread_side_effect(func, *args, **kwargs):
                return func(*args, **kwargs)
            mock_thread.side_effect = to_thread_side_effect

            result = await plugin._list_models_async(filters={}, limit=10, offset=0)

            print(f"✓ Total models: {result['total']}")
            print(f"✓ Items: {result['items']}")
            assert result["total"] == 2
            assert [item["name"] for item in result["items"]] == ["Vehicle Detector", "Product Classifier"]
            assert [item["model_type"] for item in result["items"]] == ["detection", "classification"]
            assert plugin.listing_filter_fields == [
                "project_id",
                "project_name",
                "model_group_id",
                "model_group_name",
                "model_name",
                "export_type",
                "precision",
                "model_format",
            ]
            print("✓ PASSED\n")
            return True

    print("✗ FAILED - Workspace listing did not complete\n")
    return False


async def test_list_models_base_export_reports_ignored_extra_filters():
    """Test that base export returns models without optimized-model filter warnings."""
    print("Test 6: list_models() base export ignored filters")
    print("-" * 50)

    mock_project = Mock()
    mock_project.id = "proj1"
    mock_project.name = "Detection Project"
    mock_project.get_trainable_tasks.return_value = [_mock_task("task1", "detection")]

    mock_group = Mock()
    mock_group.id = "group1"
    mock_group.name = "Detector Group"
    mock_group.task_id = "task1"

    mock_model = Mock()
    mock_model.id = "model1"
    mock_model.name = "Vehicle Detector"
    mock_model.model_group_id = "group1"
    mock_model.optimized_models = []

    with patch.dict(os.environ, {
        'GETI_HOST': 'test-host',
        'GETI_TOKEN': 'test-token',
        'GETI_WORKSPACE_ID': 'ws123'
    }):
        plugin = GetiPlugin()
        plugin.geti = Mock()
        plugin.geti.workspace_id = "ws123"
        plugin.geti.session = Mock()

        plugin._ensure_initialized = AsyncMock()
        plugin.get_projects = AsyncMock(return_value=[{
            "id": "proj1",
            "name": "Detection Project",
            "project": mock_project,
        }])

        mock_model_client = Mock()
        mock_model_client.get_all_model_groups = Mock(return_value=[mock_group])
        mock_model_client.get_latest_model_for_all_model_groups = Mock(return_value=[mock_model])
        plugin._get_or_create_model_client = AsyncMock(return_value=mock_model_client)

        with patch('plugins.geti_plugin.asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
            async def to_thread_side_effect(func, *args, **kwargs):
                return func(*args, **kwargs)
            mock_thread.side_effect = to_thread_side_effect

            result = await plugin._list_models_async(
                filters={"export_type": "base", "unsupported_filter": "x"},
                limit=10,
                offset=0,
            )

            print(f"✓ Items: {result['items']}")
            assert result["total"] == 1
            assert result["items"][0]["model_type"] == "detection"
            assert "ignored_filter_fields" not in result["items"][0]["metadata"]
            print("✓ PASSED\n")
            return True

    print("✗ FAILED - Base listing did not complete\n")
    return False


async def main():
    """Run all tests"""
    print("\n" + "=" * 50)
    print("Model Retrieval & Download Test Suite")
    print("=" * 50 + "\n")
    
    try:
        # Run tests
        test1_passed = await test_get_model_group()
        test2_passed = await test_get_model_id_by_name()
        test3_passed = await test_download_model_from_geti()
        test4_passed = await test_list_models_filters_and_paginates()
        test5_passed = await test_list_models_lists_workspace_models_without_project_scope()
        test6_passed = await test_list_models_base_export_reports_ignored_extra_filters()
        
        print("=" * 50)
        if test1_passed and test2_passed and test3_passed and test4_passed and test5_passed and test6_passed:
            print("✓ All tests PASSED!")
            print("=" * 50)
            return 0
        else:
            print("✗ Some tests FAILED")
            print("=" * 50)
            return 1
    except Exception as e:
        print(f"✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
