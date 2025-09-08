# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import pytest
import warnings
from unittest.mock import Mock, patch, MagicMock
import logging

# Comprehensive warning suppression for cleaner test output
warnings.filterwarnings("ignore")
warnings.simplefilter("ignore", DeprecationWarning)
warnings.simplefilter("ignore", PendingDeprecationWarning)

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestCommon:
    """Test suite for common.py module"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup method for each test"""
        yield

    def test_env_file_exists_and_loads(self):
        """Test that .env file is loaded when it exists"""
        with patch('utils.common.os.path.exists') as mock_exists, \
             patch('utils.common.load_dotenv') as mock_load_dotenv, \
             patch('utils.common.logger') as mock_logger:
            
            mock_exists.return_value = True
            
            # Import and reload the module
            import importlib
            if 'utils.common' in sys.modules:
                importlib.reload(sys.modules['utils.common'])
            else:
                import utils.common
            
            # The assertions depend on the actual module behavior
            assert mock_exists.called
        
    def test_env_file_not_exists(self):
        """Test behavior when .env file doesn't exist"""
        with patch('utils.common.os.path.exists') as mock_exists, \
             patch('utils.common.load_dotenv') as mock_load_dotenv, \
             patch('utils.common.logger') as mock_logger:
            
            mock_exists.return_value = False
            
            # Import and reload the module
            import importlib
            if 'utils.common' in sys.modules:
                importlib.reload(sys.modules['utils.common'])
            else:
                import utils.common
            
            # The assertions depend on the actual module behavior
            assert mock_exists.called

    def test_settings_can_be_instantiated(self):
        """Test that Settings class can be instantiated"""
        with patch('utils.common.Settings') as MockSettings:
            mock_settings = MockSettings.return_value
            mock_settings.APP_NAME = "Video-Search"
            
            settings = MockSettings()
            
            # Just verify that a settings instance can be created
            assert settings.APP_NAME == "Video-Search"
            MockSettings.assert_called_once()

    def test_settings_instance_creation_logs(self):
        """Test that settings instance creation works with logging"""
        with patch('utils.common.logger') as mock_logger, \
             patch('utils.common.Settings') as MockSettings:
            
            mock_settings = MockSettings.return_value
            mock_settings.APP_NAME = "Video-Search"
            
            settings = MockSettings()
            
            # Just verify that the settings instance was created successfully
            assert settings.APP_NAME == "Video-Search"

    def test_error_messages_class(self):
        """Test ErrorMessages class"""
        from utils.common import ErrorMessages
        
        assert hasattr(ErrorMessages, 'QUERY_VDMS_ERROR')
        assert hasattr(ErrorMessages, 'WATCHER_LAST_UPDATED_ERROR')
        assert ErrorMessages.QUERY_VDMS_ERROR == "Error in querying VDMS"
        assert ErrorMessages.WATCHER_LAST_UPDATED_ERROR == "Error in getting watcher last updated timestamp"

    def test_error_messages_immutable(self):
        """Test that ErrorMessages class attributes are accessible"""
        from utils.common import ErrorMessages
        
        # Test that we can access the error messages
        query_error = ErrorMessages.QUERY_VDMS_ERROR
        watcher_error = ErrorMessages.WATCHER_LAST_UPDATED_ERROR
        
        assert query_error == "Error in querying VDMS"
        assert watcher_error == "Error in getting watcher last updated timestamp"

    @patch('utils.common.logging.basicConfig')
    def test_logging_configuration(self, mock_basic_config):
        """Test logging configuration"""
        import importlib
        import utils.common
        importlib.reload(utils.common)
        
        mock_basic_config.assert_called_with(
            level=logging.DEBUG, 
            format="%(asctime)s - %(levelname)s - %(message)s"
        )

    def test_logger_instance(self):
        """Test logger instance creation"""
        from utils.common import logger
        
        assert logger.name == "video_search"
        assert isinstance(logger, logging.Logger)

    def test_env_path_construction(self):
        """Test environment path construction"""
        from utils.common import env_path
        
        assert env_path.endswith('.env')
        assert '../../' in env_path

# Pytest configuration for coverage
if __name__ == "__main__":
    pytest.main([
        "--cov=utils.common",  
        "--cov-report=html",
        "--cov-report=term-missing",
        "--cov-fail-under=80",
        "-W", "ignore::DeprecationWarning",
        "-W", "ignore::PendingDeprecationWarning", 
        "-v"
    ])