# test_minio_client.py
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import importlib

# Add the src directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestMinioClient:
    """Test suite for minio_client module."""
    
    def test_minio_client_module_import(self):
        """Test that the minio_client module can be imported with mocked dependencies."""
        with patch('src.utils.common.settings') as mock_settings, \
             patch('src.utils.common.logger') as mock_logger, \
             patch('minio.Minio') as mock_minio_class:
            
            # Configure mock settings
            mock_settings.MINIO_HOST = "localhost"
            mock_settings.MINIO_API_PORT = "9000"
            mock_settings.MINIO_ROOT_USER = "minioadmin"
            mock_settings.MINIO_ROOT_PASSWORD = "minioadmin123"
            
            # Configure mock Minio client
            mock_minio_instance = MagicMock()
            mock_minio_class.return_value = mock_minio_instance
            
            # Import the module (this will trigger the module-level code)
            if 'src.utils.minio_client' in sys.modules:
                del sys.modules['src.utils.minio_client']
            
            import src.utils.minio_client
            
            # Verify that Minio was called with correct parameters
            expected_url = "localhost:9000"
            mock_minio_class.assert_called_once_with(
                expected_url,
                access_key="minioadmin",
                secret_key="minioadmin123",
                secure=False
            )
            
            # Verify logger was called
            mock_logger.debug.assert_called_with("initialized minio client")
            
            # Verify module attributes exist
            assert hasattr(src.utils.minio_client, 'MINIO_URL')
            assert hasattr(src.utils.minio_client, 'client')
            assert src.utils.minio_client.MINIO_URL == expected_url
            assert src.utils.minio_client.client == mock_minio_instance
    
    def test_minio_url_construction_with_different_settings(self):
        """Test URL construction with different host and port settings."""
        with patch('src.utils.common.settings') as mock_settings, \
             patch('src.utils.common.logger') as mock_logger, \
             patch('minio.Minio') as mock_minio_class:
            
            # Configure different mock settings
            mock_settings.MINIO_HOST = "test-host"
            mock_settings.MINIO_API_PORT = "8080"
            mock_settings.MINIO_ROOT_USER = "testuser"
            mock_settings.MINIO_ROOT_PASSWORD = "testpass"
            
            mock_minio_instance = MagicMock()
            mock_minio_class.return_value = mock_minio_instance
            
            # Clear module cache and import
            if 'src.utils.minio_client' in sys.modules:
                del sys.modules['src.utils.minio_client']
            
            import src.utils.minio_client
            
            # Verify URL construction and client initialization
            expected_url = "test-host:8080"
            mock_minio_class.assert_called_once_with(
                expected_url,
                access_key="testuser",
                secret_key="testpass",
                secure=False
            )
            
            assert src.utils.minio_client.MINIO_URL == expected_url
    
    def test_secure_parameter_always_false(self):
        """Test that secure parameter is always set to False."""
        with patch('src.utils.common.settings') as mock_settings, \
             patch('src.utils.common.logger') as mock_logger, \
             patch('minio.Minio') as mock_minio_class:
            
            mock_settings.MINIO_HOST = "secure-host"
            mock_settings.MINIO_API_PORT = "9000"
            mock_settings.MINIO_ROOT_USER = "admin"
            mock_settings.MINIO_ROOT_PASSWORD = "password"
            
            mock_minio_instance = MagicMock()
            mock_minio_class.return_value = mock_minio_instance
            
            # Clear module cache and import
            if 'src.utils.minio_client' in sys.modules:
                del sys.modules['src.utils.minio_client']
            
            import src.utils.minio_client
            
            # Verify secure parameter is False
            call_args = mock_minio_class.call_args
            assert call_args is not None
            assert 'secure' in call_args.kwargs
            assert call_args.kwargs['secure'] is False
    
    def test_logger_debug_message_called(self):
        """Test that correct debug message is logged during initialization."""
        with patch('src.utils.common.settings') as mock_settings, \
             patch('src.utils.common.logger') as mock_logger, \
             patch('minio.Minio') as mock_minio_class:
            
            mock_settings.MINIO_HOST = "localhost"
            mock_settings.MINIO_API_PORT = "9000"
            mock_settings.MINIO_ROOT_USER = "minioadmin"
            mock_settings.MINIO_ROOT_PASSWORD = "minioadmin123"
            
            mock_minio_instance = MagicMock()
            mock_minio_class.return_value = mock_minio_instance
            
            # Clear module cache and import
            if 'src.utils.minio_client' in sys.modules:
                del sys.modules['src.utils.minio_client']
            
            import src.utils.minio_client
            
            # Verify debug message
            mock_logger.debug.assert_called_with("initialized minio client")
    
    def test_different_port_combinations(self):
        """Test various host and port combinations."""
        test_cases = [
            ("127.0.0.1", "9000", "127.0.0.1:9000"),
            ("minio-server", "8080", "minio-server:8080"),
            ("192.168.1.100", "9090", "192.168.1.100:9090"),
        ]
        
        for host, port, expected_url in test_cases:
            with patch('src.utils.common.settings') as mock_settings, \
                 patch('src.utils.common.logger') as mock_logger, \
                 patch('minio.Minio') as mock_minio_class:
                
                mock_settings.MINIO_HOST = host
                mock_settings.MINIO_API_PORT = port
                mock_settings.MINIO_ROOT_USER = "user"
                mock_settings.MINIO_ROOT_PASSWORD = "pass"
                
                mock_minio_instance = MagicMock()
                mock_minio_class.return_value = mock_minio_instance
                
                # Clear module cache and import
                if 'src.utils.minio_client' in sys.modules:
                    del sys.modules['src.utils.minio_client']
                
                import src.utils.minio_client
                
                # Verify correct URL construction
                mock_minio_class.assert_called_once_with(
                    expected_url,
                    access_key="user",
                    secret_key="pass",
                    secure=False
                )
                
                assert src.utils.minio_client.MINIO_URL == expected_url
    
    def test_minio_client_initialization_exception(self):
        """Test behavior when Minio client initialization fails."""
        with patch('src.utils.common.settings') as mock_settings, \
             patch('src.utils.common.logger') as mock_logger, \
             patch('minio.Minio', side_effect=Exception("Connection failed")) as mock_minio_class:
            
            mock_settings.MINIO_HOST = "localhost"
            mock_settings.MINIO_API_PORT = "9000"
            mock_settings.MINIO_ROOT_USER = "minioadmin"
            mock_settings.MINIO_ROOT_PASSWORD = "minioadmin123"
            
            # Clear module cache
            if 'src.utils.minio_client' in sys.modules:
                del sys.modules['src.utils.minio_client']
            
            # Test that the exception is propagated during import
            with pytest.raises(Exception, match="Connection failed"):
                import src.utils.minio_client
    
    def test_module_constants_structure(self):
        """Test that module has the expected structure and constants."""
        with patch('src.utils.common.settings') as mock_settings, \
             patch('src.utils.common.logger') as mock_logger, \
             patch('minio.Minio') as mock_minio_class:
            
            mock_settings.MINIO_HOST = "localhost"
            mock_settings.MINIO_API_PORT = "9000"
            mock_settings.MINIO_ROOT_USER = "minioadmin"
            mock_settings.MINIO_ROOT_PASSWORD = "minioadmin123"
            
            mock_minio_instance = MagicMock()
            mock_minio_class.return_value = mock_minio_instance
            
            # Clear module cache and import
            if 'src.utils.minio_client' in sys.modules:
                del sys.modules['src.utils.minio_client']
            
            import src.utils.minio_client
            
            # Verify module structure
            assert hasattr(src.utils.minio_client, 'MINIO_URL')
            assert hasattr(src.utils.minio_client, 'client')
            assert isinstance(src.utils.minio_client.MINIO_URL, str)
            assert src.utils.minio_client.client is not None
            
            # Verify the module imports are accessible
            assert hasattr(src.utils.minio_client, 'settings')
            assert hasattr(src.utils.minio_client, 'logger')
    
    def test_credentials_configuration(self):
        """Test that credentials are properly configured from settings."""
        test_credentials = [
            ("admin", "secret123"),
            ("minio-user", "complex-password!@#"),
            ("", ""),  # Empty credentials
        ]
        
        for username, password in test_credentials:
            with patch('src.utils.common.settings') as mock_settings, \
                 patch('src.utils.common.logger') as mock_logger, \
                 patch('minio.Minio') as mock_minio_class:
                
                mock_settings.MINIO_HOST = "localhost"
                mock_settings.MINIO_API_PORT = "9000"
                mock_settings.MINIO_ROOT_USER = username
                mock_settings.MINIO_ROOT_PASSWORD = password
                
                mock_minio_instance = MagicMock()
                mock_minio_class.return_value = mock_minio_instance
                
                # Clear module cache and import
                if 'src.utils.minio_client' in sys.modules:
                    del sys.modules['src.utils.minio_client']
                
                import src.utils.minio_client
                
                # Verify credentials are passed correctly
                call_args = mock_minio_class.call_args
                assert call_args.kwargs['access_key'] == username
                assert call_args.kwargs['secret_key'] == password


@pytest.fixture(autouse=True)
def suppress_warnings():
    """Suppress warnings for cleaner test output."""
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*Pydantic.*")
    warnings.filterwarnings("ignore", message=".*pydantic.*")


if __name__ == "__main__":
    # Run tests with coverage
    pytest.main([
        __file__,
        "-v",
        "--cov=src.utils.minio_client",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov_minio_client",
        "-W", "ignore::DeprecationWarning"
    ])
