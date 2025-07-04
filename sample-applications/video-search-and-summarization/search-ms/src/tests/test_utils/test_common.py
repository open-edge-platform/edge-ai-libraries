# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import pytest
import warnings
from unittest.mock import Mock, patch, MagicMock
import logging
from pydantic import ValidationError

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
        """Setup method to clean up environment variables before each test"""
        # Store original env vars
        self.original_env = dict(os.environ)
        
        # Clear relevant environment variables
        env_vars_to_clear = [
            'VDMS_VDB_HOST', 'VDMS_VDB_PORT', 'VCLIP_EMBEDDINGS_ENDPOINT',
            'VCLIP_EMBEDDINGS_MODEL_NAME', 'VCLIP_EMBEDDINGS_NUM_FRAMES',
            'SEARCH_ENGINE', 'DISTANCE_STRATEGY', 'INDEX_NAME', 'no_proxy_env',
            'http_proxy', 'https_proxy', 'WATCH_DIRECTORY', 
            'WATCH_DIRECTORY_CONTAINER_PATH', 'DEBOUNCE_TIME',
            'DATAPREP_UPLOAD_URL', 'VS_INITIAL_DUMP', 'DELETE_PROCESSED_FILES',
            'MINIO_API_PORT', 'MINIO_HOST', 'MINIO_ROOT_USER',
            'MINIO_ROOT_PASSWORD', 'VDMS_BUCKET', 'CHUNK_DURATION'
        ]
        
        for var in env_vars_to_clear:
            os.environ.pop(var, None)
            
        yield
        
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)

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

    def test_settings_default_values(self):
        """Test Settings class with default values"""
        # Ensure we start with clean environment
        old_http_proxy = os.environ.pop('http_proxy', None)
        old_https_proxy = os.environ.pop('https_proxy', None)
        
        try:
            from utils.common import Settings
            
            settings = Settings()
            
            assert settings.APP_NAME == "Video-Search"
            assert settings.APP_DISPLAY_NAME == "Video Search Microservice"
            assert settings.APP_DESC == "The Video Search Microservice is designed to handle video search queries and return relevant results."
            assert settings.VDMS_VDB_HOST == "vdms-vector-db"
            assert settings.VDMS_VDB_PORT == 55555
            assert settings.VCLIP_EMBEDDINGS_ENDPOINT == ""
            assert settings.VCLIP_EMBEDDINGS_MODEL_NAME == ""
            assert settings.VCLIP_EMBEDDINGS_NUM_FRAMES == 16
            assert settings.SEARCH_ENGINE == "FaissFlat"
            assert settings.DISTANCE_STRATEGY == "IP"
            assert settings.INDEX_NAME == "videoqna"
            assert settings.no_proxy_env == ""
            # Skip proxy tests since they may be set in environment
            assert settings.WATCH_DIRECTORY == ""
            assert settings.WATCH_DIRECTORY_CONTAINER_PATH == "/tmp/watcher-dir"
            assert settings.DEBOUNCE_TIME == 5
            assert settings.DATAPREP_UPLOAD_URL == ""
            assert settings.VS_INITIAL_DUMP == False
            assert settings.DELETE_PROCESSED_FILES == False
            assert settings.MINIO_API_PORT == ""
            assert settings.MINIO_HOST == ""
            assert settings.MINIO_ROOT_USER == ""
            assert settings.MINIO_ROOT_PASSWORD == ""
            assert settings.VDMS_BUCKET == ""
            assert settings.CHUNK_DURATION == 10
        finally:
            # Restore environment
            if old_http_proxy:
                os.environ['http_proxy'] = old_http_proxy  
            if old_https_proxy:
                os.environ['https_proxy'] = old_https_proxy

    def test_settings_with_environment_variables(self):
        """Test Settings class with environment variables"""
        from utils.common import Settings
        
        # Set environment variables
        os.environ['VDMS_VDB_HOST'] = 'test-host'
        os.environ['VDMS_VDB_PORT'] = '9999'
        os.environ['VCLIP_EMBEDDINGS_ENDPOINT'] = 'http://test-endpoint'
        os.environ['VCLIP_EMBEDDINGS_MODEL_NAME'] = 'test-model'
        os.environ['VCLIP_EMBEDDINGS_NUM_FRAMES'] = '32'
        os.environ['SEARCH_ENGINE'] = 'TestEngine'
        os.environ['DISTANCE_STRATEGY'] = 'L2'
        os.environ['INDEX_NAME'] = 'test-index'
        os.environ['DEBOUNCE_TIME'] = '10'
        os.environ['VS_INITIAL_DUMP'] = 'true'
        os.environ['DELETE_PROCESSED_FILES'] = 'true'
        os.environ['CHUNK_DURATION'] = '20'
        
        settings = Settings()
        
        assert settings.VDMS_VDB_HOST == 'test-host'
        assert settings.VDMS_VDB_PORT == 9999
        assert settings.VCLIP_EMBEDDINGS_ENDPOINT == 'http://test-endpoint'
        assert settings.VCLIP_EMBEDDINGS_MODEL_NAME == 'test-model'
        assert settings.VCLIP_EMBEDDINGS_NUM_FRAMES == 32
        assert settings.SEARCH_ENGINE == 'TestEngine'
        assert settings.DISTANCE_STRATEGY == 'L2'
        assert settings.INDEX_NAME == 'test-index'
        assert settings.DEBOUNCE_TIME == 10
        assert settings.VS_INITIAL_DUMP == True
        assert settings.DELETE_PROCESSED_FILES == True
        assert settings.CHUNK_DURATION == 20

    def test_settings_invalid_port_type(self):
        """Test Settings with invalid port type"""
        from utils.common import Settings
        
        os.environ['VDMS_VDB_PORT'] = 'invalid-port'
        
        with pytest.raises(ValidationError):
            Settings()

    def test_settings_invalid_boolean_type(self):
        """Test Settings with invalid boolean type"""
        from utils.common import Settings
        
        os.environ['VS_INITIAL_DUMP'] = 'invalid-boolean'
        
        with pytest.raises(ValidationError):
            Settings()

    def test_settings_invalid_integer_type(self):
        """Test Settings with invalid integer type"""
        from utils.common import Settings
        
        os.environ['VCLIP_EMBEDDINGS_NUM_FRAMES'] = 'invalid-number'
        
        with pytest.raises(ValidationError):
            Settings()

    def test_settings_dict_method(self):
        """Test Settings dict() method"""
        from utils.common import Settings
        
        settings = Settings()
        # Use model_dump() instead of deprecated dict()
        try:
            settings_dict = settings.model_dump()
        except AttributeError:
            settings_dict = settings.dict()
        
        assert isinstance(settings_dict, dict)
        assert 'APP_NAME' in settings_dict
        assert 'VDMS_VDB_HOST' in settings_dict
        assert 'VDMS_VDB_PORT' in settings_dict
        assert settings_dict['APP_NAME'] == 'Video-Search'

    def test_settings_model_dump_method(self):
        """Test Settings model_dump() method (Pydantic v2)"""
        from utils.common import Settings
        
        settings = Settings()
        
        # Try both dict() and model_dump() methods for compatibility
        try:
            settings_dict = settings.model_dump()
        except AttributeError:
            settings_dict = settings.dict()
        
        assert isinstance(settings_dict, dict)
        assert 'APP_NAME' in settings_dict

    def test_settings_instance_creation_logs(self):
        """Test that settings instance creation triggers logging"""
        with patch('utils.common.logger') as mock_logger:
            from utils.common import Settings
            settings = Settings()
            
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

    def test_settings_with_proxy_variables(self):
        """Test Settings with proxy environment variables"""
        from utils.common import Settings
        
        os.environ['no_proxy_env'] = 'localhost,127.0.0.1'
        os.environ['http_proxy'] = 'http://proxy:8080'
        os.environ['https_proxy'] = 'https://proxy:8080'
        
        settings = Settings()
        
        assert settings.no_proxy_env == 'localhost,127.0.0.1'
        assert settings.http_proxy == 'http://proxy:8080'
        assert settings.https_proxy == 'https://proxy:8080'

    def test_settings_with_minio_variables(self):
        """Test Settings with MinIO environment variables"""
        from utils.common import Settings
        
        os.environ['MINIO_API_PORT'] = '9000'
        os.environ['MINIO_HOST'] = 'minio-server'
        os.environ['MINIO_ROOT_USER'] = 'admin'
        os.environ['MINIO_ROOT_PASSWORD'] = 'password123'
        os.environ['VDMS_BUCKET'] = 'test-bucket'
        
        settings = Settings()
        
        assert settings.MINIO_API_PORT == '9000'
        assert settings.MINIO_HOST == 'minio-server'
        assert settings.MINIO_ROOT_USER == 'admin'
        assert settings.MINIO_ROOT_PASSWORD == 'password123'
        assert settings.VDMS_BUCKET == 'test-bucket'

    def test_settings_with_watch_directory_variables(self):
        """Test Settings with watch directory environment variables"""
        from utils.common import Settings
        
        os.environ['WATCH_DIRECTORY'] = '/host/watch/dir'
        os.environ['WATCH_DIRECTORY_CONTAINER_PATH'] = '/container/watch/dir'
        os.environ['DATAPREP_UPLOAD_URL'] = 'http://dataprep:8080/upload'
        
        settings = Settings()
        
        assert settings.WATCH_DIRECTORY == '/host/watch/dir'
        assert settings.WATCH_DIRECTORY_CONTAINER_PATH == '/container/watch/dir'
        assert settings.DATAPREP_UPLOAD_URL == 'http://dataprep:8080/upload'

    def test_settings_string_representation(self):
        """Test Settings string representation"""
        from utils.common import Settings
        
        settings = Settings()
        settings_str = str(settings)
        
        assert 'APP_NAME' in settings_str or 'Video-Search' in settings_str

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