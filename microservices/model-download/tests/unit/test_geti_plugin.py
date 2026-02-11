#!/usr/bin/env python
"""
Test script to verify model retrieval and download methods work with the reference implementation pattern.
"""
import asyncio
import os
import sys
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from plugins.geti_plugin import GetiPlugin


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
    """Test that _download_model_from_geti uses the correct SDK pattern"""
    print("Test 3: _download_model_from_geti()")
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
        
        with patch.object(plugin, 'get_projects', new_callable=AsyncMock) as mock_get_projects:
            mock_get_projects.return_value = [{"project": mock_project}]
            
            with patch('plugins.geti_plugin.ModelClient') as mock_model_client_class:
                mock_model_client = Mock()
                mock_model_client._get_model_detail = Mock(return_value=mock_base_model)
                mock_model_client._download_model = Mock()
                mock_model_client_class.return_value = mock_model_client
                
                with patch('plugins.geti_plugin.asyncio.to_thread', new_callable=AsyncMock) as mock_thread:
                    async def to_thread_side_effect(func, *args):
                        return func(*args)
                    mock_thread.side_effect = to_thread_side_effect
                    
                    with patch('os.makedirs'), \
                         patch('os.path.exists', return_value=False), \
                         patch('os.path.join', side_effect=lambda *args: '/'.join(args)):
                        
                        result = await plugin._download_model_from_geti(
                            model_id="model1",
                            output_dir="/tmp/models",
                            model_name="Base Model",
                            export_type="base",
                            project_id="proj1",
                            model_group_id="group1"
                        )
                        
                        print(f"✓ Download returned: {result}")
                        print(f"✓ ModelClient._get_model_detail was called with correct args")
                        mock_model_client._get_model_detail.assert_called_once()
                        print(f"✓ ModelClient._download_model was called for base model")
                        mock_model_client._download_model.assert_called()
                        print("✓ PASSED\n")
    return True


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
        
        print("=" * 50)
        if test1_passed and test2_passed and test3_passed:
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
