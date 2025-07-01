# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, mock_open, MagicMock
import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout


class TestUtils:
    """Test suite for src/utils/utils.py"""

    def setup_method(self):
        """Reset uploaded_files set before each test"""
        import src.utils.utils
        src.utils.utils.uploaded_files.clear()

    def test_sanitize_file_path_normal_filename(self):
        """Test sanitize_file_path with normal filename"""
        from src.utils.utils import sanitize_file_path
        
        result = sanitize_file_path("/path/to/video_file-1.mp4")
        assert result == "video_file-1.mp4"

    def test_sanitize_file_path_special_characters(self):
        """Test sanitize_file_path with special characters"""
        from src.utils.utils import sanitize_file_path
        
        result = sanitize_file_path("/path/to/video@#$%^&*()file!.mp4")
        assert result == "video_________file_.mp4"

    def test_sanitize_file_path_unicode_characters(self):
        """Test sanitize_file_path with unicode characters"""
        from src.utils.utils import sanitize_file_path
        
        result = sanitize_file_path("/path/to/vidéo_文件.mp4")
        assert result == "vid_o___.mp4"

    def test_sanitize_file_path_empty_filename(self):
        """Test sanitize_file_path with empty path"""
        from src.utils.utils import sanitize_file_path
        
        result = sanitize_file_path("")
        assert result == ""

    def test_sanitize_file_path_only_path(self):
        """Test sanitize_file_path with only directory path"""
        from src.utils.utils import sanitize_file_path
        
        result = sanitize_file_path("/path/to/directory/")
        assert result == ""

    @patch('src.utils.utils.settings')
    def test_should_use_no_proxy_matching_domain(self, mock_settings):
        """Test should_use_no_proxy with matching domain"""
        from src.utils.utils import should_use_no_proxy
        
        mock_settings.no_proxy_env = "localhost,127.0.0.1,.local"
        
        assert should_use_no_proxy("http://localhost:8080/api") == True
        assert should_use_no_proxy("https://test.local/endpoint") == True

    @patch('src.utils.utils.settings')
    def test_should_use_no_proxy_non_matching_domain(self, mock_settings):
        """Test should_use_no_proxy with non-matching domain"""
        from src.utils.utils import should_use_no_proxy
        
        mock_settings.no_proxy_env = "localhost,127.0.0.1,.local"
        
        assert should_use_no_proxy("http://example.com/api") == False
        assert should_use_no_proxy("https://google.com/search") == False

    @patch('src.utils.utils.settings')
    def test_should_use_no_proxy_empty_hostname(self, mock_settings):
        """Test should_use_no_proxy with invalid URL"""
        from src.utils.utils import should_use_no_proxy
        
        mock_settings.no_proxy_env = "localhost,127.0.0.1"
        
        assert should_use_no_proxy("invalid-url") == False

    @patch('src.utils.utils.settings')
    def test_should_use_no_proxy_empty_no_proxy(self, mock_settings):
        """Test should_use_no_proxy with empty no_proxy setting"""
        from src.utils.utils import should_use_no_proxy
        
        mock_settings.no_proxy_env = ""
        
        assert should_use_no_proxy("http://localhost:8080/api") == True

    @patch('src.utils.utils.settings')
    @patch('src.utils.utils.requests.post')
    @patch('src.utils.utils.should_use_no_proxy')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    @patch('src.utils.utils.os.remove')
    def test_upload_videos_to_dataprep_success_with_delete(self, mock_remove, mock_file, mock_no_proxy, mock_post, mock_settings):
        """Test successful upload with file deletion"""
        from src.utils.utils import upload_videos_to_dataprep
        
        # Setup mocks
        mock_settings.DATAPREP_UPLOAD_URL = "http://example.com/upload"
        mock_settings.DELETE_PROCESSED_FILES = True
        mock_settings.CHUNK_DURATION = 30
        mock_settings.http_proxy = "http://proxy:8080"
        mock_settings.https_proxy = "https://proxy:8080"
        mock_no_proxy.return_value = False
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = upload_videos_to_dataprep(["/test/video1.mp4"])
        
        assert result == True
        mock_post.assert_called_once()
        mock_remove.assert_called_once_with("/test/video1.mp4")

    @patch('src.utils.utils.settings')
    @patch('src.utils.utils.requests.post')
    @patch('src.utils.utils.should_use_no_proxy')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    def test_upload_videos_to_dataprep_success_no_delete(self, mock_file, mock_no_proxy, mock_post, mock_settings):
        """Test successful upload without file deletion"""
        from src.utils.utils import upload_videos_to_dataprep
        
        # Setup mocks
        mock_settings.DATAPREP_UPLOAD_URL = "http://example.com/upload"
        mock_settings.DELETE_PROCESSED_FILES = False
        mock_settings.CHUNK_DURATION = 30
        mock_no_proxy.return_value = True
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = upload_videos_to_dataprep(["/test/video1.mp4"])
        
        assert result == True
        # Verify no_proxy was used (proxies=None)
        call_args = mock_post.call_args
        assert call_args[1]['proxies'] is None

    @patch('src.utils.utils.settings')
    @patch('src.utils.utils.requests.post')
    @patch('src.utils.utils.should_use_no_proxy')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    def test_upload_videos_to_dataprep_with_proxy(self, mock_file, mock_no_proxy, mock_post, mock_settings):
        """Test upload using proxy settings"""
        from src.utils.utils import upload_videos_to_dataprep
        
        # Setup mocks
        mock_settings.DATAPREP_UPLOAD_URL = "http://example.com/upload"
        mock_settings.DELETE_PROCESSED_FILES = False
        mock_settings.CHUNK_DURATION = 30
        mock_settings.http_proxy = "http://proxy:8080"
        mock_settings.https_proxy = "https://proxy:8080"
        mock_no_proxy.return_value = False
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = upload_videos_to_dataprep(["/test/video1.mp4"])
        
        assert result == True
        # Verify proxy was used
        call_args = mock_post.call_args
        expected_proxies = {
            "http": "http://proxy:8080",
            "https": "https://proxy:8080",
        }
        assert call_args[1]['proxies'] == expected_proxies

    @patch('src.utils.utils.settings')
    @patch('src.utils.utils.requests.post')
    @patch('src.utils.utils.should_use_no_proxy')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    def test_upload_videos_to_dataprep_http_error_422(self, mock_file, mock_no_proxy, mock_post, mock_settings):
        """Test upload with HTTP 422 error"""
        from src.utils.utils import upload_videos_to_dataprep
        
        # Setup mocks
        mock_settings.DATAPREP_UPLOAD_URL = "http://example.com/upload"
        mock_settings.DELETE_PROCESSED_FILES = False
        mock_settings.CHUNK_DURATION = 30
        mock_no_proxy.return_value = False
        
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.url = "http://example.com/upload"
        mock_response.raise_for_status.side_effect = HTTPError("422 Client Error")
        mock_post.return_value = mock_response
        
        result = upload_videos_to_dataprep(["/test/video1.mp4"])
        
        assert result == False

    @patch('src.utils.utils.settings')
    @patch('src.utils.utils.requests.post')
    @patch('src.utils.utils.should_use_no_proxy')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    def test_upload_videos_to_dataprep_http_error_other(self, mock_file, mock_no_proxy, mock_post, mock_settings):
        """Test upload with HTTP error other than 422"""
        from src.utils.utils import upload_videos_to_dataprep
        
        # Setup mocks
        mock_settings.DATAPREP_UPLOAD_URL = "http://example.com/upload"
        mock_settings.DELETE_PROCESSED_FILES = False
        mock_settings.CHUNK_DURATION = 30
        mock_no_proxy.return_value = False
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = HTTPError("500 Server Error")
        mock_post.return_value = mock_response
        
        result = upload_videos_to_dataprep(["/test/video1.mp4"])
        
        assert result == False

    @patch('src.utils.utils.settings')
    @patch('src.utils.utils.requests.post')
    @patch('src.utils.utils.should_use_no_proxy')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    def test_upload_videos_to_dataprep_connection_error(self, mock_file, mock_no_proxy, mock_post, mock_settings):
        """Test upload with connection error"""
        from src.utils.utils import upload_videos_to_dataprep
        
        # Setup mocks
        mock_settings.DATAPREP_UPLOAD_URL = "http://example.com/upload"
        mock_settings.DELETE_PROCESSED_FILES = False
        mock_settings.CHUNK_DURATION = 30
        mock_no_proxy.return_value = False
        
        mock_post.side_effect = ConnectionError("Connection failed")
        
        result = upload_videos_to_dataprep(["/test/video1.mp4"])
        
        assert result == False

    @patch('src.utils.utils.settings')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    def test_upload_videos_to_dataprep_file_open_error(self, mock_file, mock_settings):
        """Test upload when file cannot be opened"""
        from src.utils.utils import upload_videos_to_dataprep
        
        # Setup mocks
        mock_settings.DATAPREP_UPLOAD_URL = "http://example.com/upload"
        mock_settings.DELETE_PROCESSED_FILES = False
        mock_settings.CHUNK_DURATION = 30
        
        mock_file.side_effect = FileNotFoundError("File not found")
        
        result = upload_videos_to_dataprep(["/test/nonexistent.mp4"])
        
        assert result == False

    def test_upload_videos_to_dataprep_already_uploaded(self):
        """Test upload skips already uploaded files"""
        from src.utils.utils import upload_videos_to_dataprep, uploaded_files
        
        # Add file to uploaded_files set
        uploaded_files.add("/test/video1.mp4")
        
        with patch('src.utils.utils.requests.post') as mock_post:
            result = upload_videos_to_dataprep(["/test/video1.mp4"])
            
            # Should return True but not make any requests
            assert result == True
            mock_post.assert_not_called()

    @patch('src.utils.utils.settings')
    @patch('src.utils.utils.requests.post')
    @patch('src.utils.utils.should_use_no_proxy')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    def test_upload_videos_to_dataprep_multiple_files_mixed_results(self, mock_file, mock_no_proxy, mock_post, mock_settings):
        """Test upload with multiple files where some succeed and some fail"""
        from src.utils.utils import upload_videos_to_dataprep
        
        # Setup mocks
        mock_settings.DATAPREP_UPLOAD_URL = "http://example.com/upload"
        mock_settings.DELETE_PROCESSED_FILES = False
        mock_settings.CHUNK_DURATION = 30
        mock_no_proxy.return_value = False
        
        # First call succeeds, second call fails
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status.return_value = None
        
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_fail.raise_for_status.side_effect = HTTPError("500 Server Error")
        
        mock_post.side_effect = [mock_response_success, mock_response_fail]
        
        result = upload_videos_to_dataprep(["/test/video1.mp4", "/test/video2.mp4"])
        
        assert result == False  # Should return False if any upload fails
        assert mock_post.call_count == 2

    @patch('src.utils.utils.settings')
    @patch('src.utils.utils.requests.post')
    @patch('src.utils.utils.should_use_no_proxy')
    @patch('builtins.open', new_callable=mock_open, read_data=b"fake video data")
    def test_upload_videos_to_dataprep_empty_file_list(self, mock_file, mock_no_proxy, mock_post, mock_settings):
        """Test upload with empty file list"""
        from src.utils.utils import upload_videos_to_dataprep
        
        result = upload_videos_to_dataprep([])
        
        assert result == True
        mock_post.assert_not_called()

    @patch('src.utils.utils.logger')
    @patch('src.utils.utils.settings')
    def test_should_use_no_proxy_logging(self, mock_settings, mock_logger):
        """Test should_use_no_proxy logging behavior"""
        from src.utils.utils import should_use_no_proxy
        
        mock_settings.no_proxy_env = "localhost,127.0.0.1"
        
        # Test matching domain
        result = should_use_no_proxy("http://localhost:8080/api")
        assert result == True
        
        # Verify debug logging
        mock_logger.debug.assert_any_call(
            "Checking no_proxy for hostname: localhost against no_proxy domains: localhost,127.0.0.1"
        )
        mock_logger.debug.assert_any_call(
            "Hostname localhost matches no_proxy domain localhost"
        )

    @patch('src.utils.utils.logger')
    @patch('src.utils.utils.settings')
    def test_should_use_no_proxy_no_match_logging(self, mock_settings, mock_logger):
        """Test should_use_no_proxy logging when no match found"""
        from src.utils.utils import should_use_no_proxy
        
        mock_settings.no_proxy_env = "localhost,127.0.0.1"
        
        # Test non-matching domain
        result = should_use_no_proxy("http://example.com/api")
        assert result == False
        
        # Verify debug logging
        mock_logger.debug.assert_any_call(
            "Hostname example.com does not match any no_proxy domains"
        )

    def test_uploaded_files_global_variable(self):
        """Test that uploaded_files global variable works correctly"""
        from src.utils.utils import uploaded_files
        
        # Should start empty
        assert len(uploaded_files) == 0
        
        # Add some files
        uploaded_files.add("file1.mp4")
        uploaded_files.add("file2.mp4")
        
        assert len(uploaded_files) == 2
        assert "file1.mp4" in uploaded_files
        assert "file2.mp4" in uploaded_files
        
        # Test duplicate addition
        uploaded_files.add("file1.mp4")
        assert len(uploaded_files) == 2  # Should still be 2
