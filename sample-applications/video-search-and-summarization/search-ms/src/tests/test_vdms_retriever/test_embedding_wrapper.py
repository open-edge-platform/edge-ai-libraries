# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
from requests.exceptions import RequestException, HTTPError
from src.vdms_retriever.embedding_wrapper import should_use_no_proxy, vCLIPEmbeddingsWrapper


class TestShouldUseNoProxy:
    """Test cases for should_use_no_proxy function."""
    
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_should_use_no_proxy_match_exact_domain(self, mock_settings):
        """Test exact domain match in no_proxy."""
        mock_settings.no_proxy_env = "example.com,localhost"
        
        result = should_use_no_proxy("http://example.com/api")
        assert result is True
    
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_should_use_no_proxy_match_subdomain(self, mock_settings):
        """Test subdomain match in no_proxy."""
        mock_settings.no_proxy_env = "example.com,localhost"
        
        result = should_use_no_proxy("http://api.example.com/embeddings")
        assert result is True
    
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_should_use_no_proxy_no_match(self, mock_settings):
        """Test no match in no_proxy."""
        mock_settings.no_proxy_env = "example.com,localhost"
        
        result = should_use_no_proxy("http://different.com/api")
        assert result is False
    
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_should_use_no_proxy_empty_no_proxy(self, mock_settings):
        """Test with empty no_proxy setting."""
        mock_settings.no_proxy_env = ""
        
        result = should_use_no_proxy("http://example.com/api")
        assert result is True
    
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_should_use_no_proxy_localhost(self, mock_settings):
        """Test localhost match."""
        mock_settings.no_proxy_env = "localhost,127.0.0.1"
        
        result = should_use_no_proxy("http://localhost:8080/api")
        assert result is True
    
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_should_use_no_proxy_invalid_url(self, mock_settings):
        """Test with invalid URL."""
        mock_settings.no_proxy_env = "example.com"
        
        result = should_use_no_proxy("invalid-url")
        assert result is False


class TestVCLIPEmbeddingsWrapper:
    """Test cases for vCLIPEmbeddingsWrapper class."""
    
    @pytest.fixture
    def wrapper(self):
        """Create a vCLIPEmbeddingsWrapper instance for testing."""
        return vCLIPEmbeddingsWrapper(
            api_url="http://localhost:8080/embeddings",
            model_name="vclip-model",
            num_frames=8
        )
    
    @pytest.fixture
    def mock_response(self):
        """Create a mock response for requests."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embedding": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]}
        mock_resp.raise_for_status.return_value = None
        return mock_resp
    
    @pytest.fixture
    def mock_single_response(self):
        """Create a mock response for single embedding."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    @patch('src.vdms_retriever.embedding_wrapper.should_use_no_proxy')
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_embed_documents_success(self, mock_settings, mock_no_proxy, mock_post, wrapper, mock_response):
        """Test successful document embedding."""
        mock_no_proxy.return_value = False
        mock_settings.http_proxy = "http://proxy:8080"
        mock_settings.https_proxy = "https://proxy:8080"
        mock_post.return_value = mock_response
        
        texts = ["hello world", "test document"]
        result = wrapper.embed_documents(texts)
        
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_post.assert_called_once_with(
            "http://localhost:8080/embeddings",
            json={
                "model": "vclip-model",
                "input": {"type": "text", "text": texts},
                "encoding_format": "float",
            },
            proxies={"http": "http://proxy:8080", "https": "https://proxy:8080"}
        )

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    @patch('src.vdms_retriever.embedding_wrapper.should_use_no_proxy')
    def test_embed_documents_with_no_proxy(self, mock_no_proxy, mock_post, wrapper, mock_response):
        """Test document embedding with no proxy."""
        mock_no_proxy.return_value = True
        mock_post.return_value = mock_response
        
        texts = ["hello world"]
        result = wrapper.embed_documents(texts)
        
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_post.assert_called_once_with(
            "http://localhost:8080/embeddings",
            json={
                "model": "vclip-model",
                "input": {"type": "text", "text": texts},
                "encoding_format": "float",
            },
            proxies=None
        )

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    def test_embed_documents_request_exception(self, mock_post, wrapper):
        """Test document embedding with request exception."""
        mock_post.side_effect = RequestException("Network error")
        
        with pytest.raises(Exception, match="Error creating embedding"):
            wrapper.embed_documents(["test"])

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    @patch('src.vdms_retriever.embedding_wrapper.should_use_no_proxy')
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_embed_query_success(self, mock_settings, mock_no_proxy, mock_post, wrapper, mock_single_response):
        """Test successful query embedding."""
        mock_no_proxy.return_value = False
        mock_settings.http_proxy = "http://proxy:8080"
        mock_settings.https_proxy = "https://proxy:8080"
        mock_post.return_value = mock_single_response
        
        text = "search query"
        result = wrapper.embed_query(text)
        
        assert result == [0.1, 0.2, 0.3]
        mock_post.assert_called_once_with(
            "http://localhost:8080/embeddings",
            json={
                "model": "vclip-model",
                "input": {"type": "text", "text": text},
                "encoding_format": "float",
            },
            proxies={"http": "http://proxy:8080", "https": "https://proxy:8080"}
        )

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    def test_embed_query_request_exception(self, mock_post, wrapper):
        """Test query embedding with request exception."""
        mock_post.side_effect = RequestException("Network error")
        
        with pytest.raises(Exception, match="Error creating embedding"):
            wrapper.embed_query("test query")

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    @patch('src.vdms_retriever.embedding_wrapper.should_use_no_proxy')
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_embed_video_success(self, mock_settings, mock_no_proxy, mock_post, wrapper):
        """Test successful video embedding."""
        mock_no_proxy.return_value = False
        mock_settings.http_proxy = "http://proxy:8080"
        mock_settings.https_proxy = "https://proxy:8080"
        
        # Mock multiple responses for multiple video paths
        mock_resp1 = Mock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_resp1.raise_for_status.return_value = None
        
        mock_resp2 = Mock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {"embedding": [0.4, 0.5, 0.6]}
        mock_resp2.raise_for_status.return_value = None
        
        mock_post.side_effect = [mock_resp1, mock_resp2]
        
        paths = ["/path/to/video1.mp4", "/path/to/video2.mp4"]
        kwargs = {"start_time": [10.0], "clip_duration": [5.0]}
        
        result = wrapper.embed_video(paths, **kwargs)
        
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        assert mock_post.call_count == 2
        
        # Check first call
        first_call = mock_post.call_args_list[0]
        assert first_call[1]["json"]["input"]["video_path"] == "/path/to/video1.mp4"
        assert first_call[1]["json"]["input"]["segment_config"]["startOffsetSec"] == 10.0
        assert first_call[1]["json"]["input"]["segment_config"]["clip_duration"] == 5.0
        assert first_call[1]["json"]["input"]["segment_config"]["num_frames"] == 8

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    def test_embed_video_request_exception(self, mock_post, wrapper):
        """Test video embedding with request exception."""
        mock_post.side_effect = RequestException("Network error")
        
        paths = ["/path/to/video.mp4"]
        kwargs = {"start_time": [10.0], "clip_duration": [5.0]}
        
        with pytest.raises(Exception, match="Error creating embedding"):
            wrapper.embed_video(paths, **kwargs)

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    @patch('src.vdms_retriever.embedding_wrapper.should_use_no_proxy')
    @patch('src.vdms_retriever.embedding_wrapper.settings')
    def test_get_embedding_length_success(self, mock_settings, mock_no_proxy, mock_post, wrapper):
        """Test successful embedding length retrieval."""
        mock_no_proxy.return_value = False
        mock_settings.http_proxy = "http://proxy:8080"
        mock_settings.https_proxy = "https://proxy:8080"
        
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embedding": [[0.1, 0.2, 0.3, 0.4, 0.5]]}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp
        
        result = wrapper.get_embedding_length()
        
        assert result == 5
        mock_post.assert_called_once_with(
            "http://localhost:8080/embeddings",
            json={
                "model": "vclip-model",
                "input": {"type": "text", "text": ["sample_text"]},
                "encoding_format": "float",
            },
            proxies={"http": "http://proxy:8080", "https": "https://proxy:8080"}
        )

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    def test_get_embedding_length_request_exception(self, mock_post, wrapper):
        """Test embedding length retrieval with request exception."""
        mock_post.side_effect = RequestException("Network error")
        
        with pytest.raises(Exception, match="Error getting embedding length"):
            wrapper.get_embedding_length()

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    def test_http_error_handling(self, mock_post, wrapper):
        """Test HTTP error handling."""
        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = HTTPError("Server error")
        mock_post.return_value = mock_resp
        
        with pytest.raises(Exception, match="Error creating embedding"):
            wrapper.embed_documents(["test"])

    def test_wrapper_initialization(self):
        """Test wrapper initialization with valid parameters."""
        wrapper = vCLIPEmbeddingsWrapper(
            api_url="http://test.com",
            model_name="test-model",
            num_frames=16
        )
        
        assert wrapper.api_url == "http://test.com"
        assert wrapper.model_name == "test-model"
        assert wrapper.num_frames == 16

    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    @patch('src.vdms_retriever.embedding_wrapper.should_use_no_proxy')
    def test_embed_video_single_path(self, mock_no_proxy, mock_post, wrapper):
        """Test video embedding with single path."""
        mock_no_proxy.return_value = True
        
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp
        
        paths = ["/path/to/video.mp4"]
        kwargs = {"start_time": [0.0], "clip_duration": [10.0]}
        
        result = wrapper.embed_video(paths, **kwargs)
        
        assert result == [[0.1, 0.2, 0.3]]
        assert mock_post.call_count == 1

    @patch('src.vdms_retriever.embedding_wrapper.logger')
    @patch('src.vdms_retriever.embedding_wrapper.requests.post')
    def test_logging_calls(self, mock_post, mock_logger, wrapper, mock_response):
        """Test that logging calls are made correctly."""
        mock_post.return_value = mock_response
        
        wrapper.embed_documents(["test"])
        
        # Verify debug logging calls
        mock_logger.debug.assert_any_call("Embedding documents: ['test']")
        mock_logger.debug.assert_any_call("Response status code: 200")