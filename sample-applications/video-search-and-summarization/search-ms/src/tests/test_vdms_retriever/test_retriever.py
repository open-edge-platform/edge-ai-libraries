# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock the vdms module before any imports that depend on it
sys.modules['vdms'] = MagicMock()

# Mock the langchain_community.vectorstores.vdms module
mock_vdms_module = MagicMock()
mock_vdms_client = MagicMock()
mock_vdms = MagicMock()

mock_vdms_module.VDMS = mock_vdms
mock_vdms_module.VDMS_Client = mock_vdms_client
sys.modules['langchain_community.vectorstores.vdms'] = mock_vdms_module


class TestRetrieverModule:
    """Test cases for retriever module."""

    def test_module_level_client_creation(self):
        """Test that client is created at module level."""
        # Since the client is created at module import time,
        # we can only test that it exists and is not None
        from src.vdms_retriever.retriever import client
        assert client is not None

    def test_debug_flag(self):
        """Test DEBUG flag is set correctly."""
        from src.vdms_retriever.retriever import DEBUG
        assert DEBUG is False

    @patch('src.vdms_retriever.retriever.VDMS')
    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    @patch('src.vdms_retriever.retriever.client')
    def test_get_vectordb_success(self, mock_client, mock_settings, mock_embedding_wrapper, mock_vdms):
        """Test successful vector database initialization."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup mock settings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = "http://localhost:8080/embeddings"
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = "vclip-model"
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 8
        mock_settings.INDEX_NAME = "test_index"
        mock_settings.DISTANCE_STRATEGY = "cosine"
        mock_settings.SEARCH_ENGINE = "faiss"

        # Setup mock embedding wrapper
        mock_embedding_instance = Mock()
        mock_embedding_instance.get_embedding_length.return_value = 512
        mock_embedding_wrapper.return_value = mock_embedding_instance

        # Setup mock VDMS
        mock_vdms_instance = Mock()
        mock_vdms.return_value = mock_vdms_instance

        # Call the function
        result = get_vectordb()

        # Verify embedding wrapper was created correctly
        mock_embedding_wrapper.assert_called_once_with(
            api_url="http://localhost:8080/embeddings",
            model_name="vclip-model",
            num_frames=8
        )

        # Verify get_embedding_length was called
        mock_embedding_instance.get_embedding_length.assert_called_once()

        # Verify VDMS was initialized correctly
        mock_vdms.assert_called_once_with(
            client=mock_client,
            embedding=mock_embedding_instance,
            collection_name="test_index",
            embedding_dimensions=512,
            distance_strategy="cosine",
            engine="faiss"
        )

        # Verify return value
        assert result == mock_vdms_instance

    @patch('src.vdms_retriever.retriever.VDMS')
    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    @patch('src.vdms_retriever.retriever.client')
    def test_get_vectordb_different_settings(self, mock_client, mock_settings, mock_embedding_wrapper, mock_vdms):
        """Test vector database initialization with different settings."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup different mock settings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = "http://api.example.com/embed"
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = "custom-model"
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 16
        mock_settings.INDEX_NAME = "custom_index"
        mock_settings.DISTANCE_STRATEGY = "euclidean"
        mock_settings.SEARCH_ENGINE = "annoy"

        # Setup mock embedding wrapper
        mock_embedding_instance = Mock()
        mock_embedding_instance.get_embedding_length.return_value = 1024
        mock_embedding_wrapper.return_value = mock_embedding_instance

        # Setup mock VDMS
        mock_vdms_instance = Mock()
        mock_vdms.return_value = mock_vdms_instance

        # Call the function
        result = get_vectordb()

        # Verify embedding wrapper was created with different settings
        mock_embedding_wrapper.assert_called_once_with(
            api_url="http://api.example.com/embed",
            model_name="custom-model",
            num_frames=16
        )

        # Verify VDMS was initialized with different settings
        mock_vdms.assert_called_once_with(
            client=mock_client,
            embedding=mock_embedding_instance,
            collection_name="custom_index",
            embedding_dimensions=1024,
            distance_strategy="euclidean",
            engine="annoy"
        )

        assert result == mock_vdms_instance

    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    def test_get_vectordb_embedding_wrapper_exception(self, mock_settings, mock_embedding_wrapper):
        """Test get_vectordb when embedding wrapper initialization fails."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup mock settings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = "http://localhost:8080/embeddings"
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = "vclip-model"
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 8

        # Make embedding wrapper raise an exception
        mock_embedding_wrapper.side_effect = Exception("Embedding initialization failed")

        # Verify exception is propagated
        with pytest.raises(Exception, match="Embedding initialization failed"):
            get_vectordb()

    @patch('src.vdms_retriever.retriever.VDMS')
    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    def test_get_vectordb_embedding_length_exception(self, mock_settings, mock_embedding_wrapper, mock_vdms):
        """Test get_vectordb when get_embedding_length fails."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup mock settings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = "http://localhost:8080/embeddings"
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = "vclip-model"
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 8

        # Setup mock embedding wrapper that fails on get_embedding_length
        mock_embedding_instance = Mock()
        mock_embedding_instance.get_embedding_length.side_effect = Exception("Failed to get embedding length")
        mock_embedding_wrapper.return_value = mock_embedding_instance

        # Verify exception is propagated
        with pytest.raises(Exception, match="Failed to get embedding length"):
            get_vectordb()

    @patch('src.vdms_retriever.retriever.VDMS')
    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    @patch('src.vdms_retriever.retriever.client')
    def test_get_vectordb_vdms_initialization_exception(self, mock_client, mock_settings, mock_embedding_wrapper, mock_vdms):
        """Test get_vectordb when VDMS initialization fails."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup mock settings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = "http://localhost:8080/embeddings"
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = "vclip-model"
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 8
        mock_settings.INDEX_NAME = "test_index"
        mock_settings.DISTANCE_STRATEGY = "cosine"
        mock_settings.SEARCH_ENGINE = "faiss"

        # Setup mock embedding wrapper
        mock_embedding_instance = Mock()
        mock_embedding_instance.get_embedding_length.return_value = 512
        mock_embedding_wrapper.return_value = mock_embedding_instance

        # Make VDMS initialization fail
        mock_vdms.side_effect = Exception("VDMS initialization failed")

        # Verify exception is propagated
        with pytest.raises(Exception, match="VDMS initialization failed"):
            get_vectordb()

    @patch('src.vdms_retriever.retriever.VDMS')
    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    @patch('src.vdms_retriever.retriever.client')
    def test_get_vectordb_zero_dimensions(self, mock_client, mock_settings, mock_embedding_wrapper, mock_vdms):
        """Test get_vectordb with zero embedding dimensions."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup mock settings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = "http://localhost:8080/embeddings"
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = "vclip-model"
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 8
        mock_settings.INDEX_NAME = "test_index"
        mock_settings.DISTANCE_STRATEGY = "cosine"
        mock_settings.SEARCH_ENGINE = "faiss"

        # Setup mock embedding wrapper with zero dimensions
        mock_embedding_instance = Mock()
        mock_embedding_instance.get_embedding_length.return_value = 0
        mock_embedding_wrapper.return_value = mock_embedding_instance

        # Setup mock VDMS
        mock_vdms_instance = Mock()
        mock_vdms.return_value = mock_vdms_instance

        # Call the function
        result = get_vectordb()

        # Verify VDMS was called with zero dimensions
        mock_vdms.assert_called_once_with(
            client=mock_client,
            embedding=mock_embedding_instance,
            collection_name="test_index",
            embedding_dimensions=0,
            distance_strategy="cosine",
            engine="faiss"
        )

        assert result == mock_vdms_instance

    @patch('src.vdms_retriever.retriever.VDMS')
    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    @patch('src.vdms_retriever.retriever.client')
    def test_get_vectordb_large_dimensions(self, mock_client, mock_settings, mock_embedding_wrapper, mock_vdms):
        """Test get_vectordb with large embedding dimensions."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup mock settings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = "http://localhost:8080/embeddings"
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = "vclip-model"
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 8
        mock_settings.INDEX_NAME = "test_index"
        mock_settings.DISTANCE_STRATEGY = "cosine"
        mock_settings.SEARCH_ENGINE = "faiss"

        # Setup mock embedding wrapper with large dimensions
        mock_embedding_instance = Mock()
        mock_embedding_instance.get_embedding_length.return_value = 4096
        mock_embedding_wrapper.return_value = mock_embedding_instance

        # Setup mock VDMS
        mock_vdms_instance = Mock()
        mock_vdms.return_value = mock_vdms_instance

        # Call the function
        result = get_vectordb()

        # Verify VDMS was called with large dimensions
        mock_vdms.assert_called_once_with(
            client=mock_client,
            embedding=mock_embedding_instance,
            collection_name="test_index",
            embedding_dimensions=4096,
            distance_strategy="cosine",
            engine="faiss"
        )

        assert result == mock_vdms_instance

    @patch('src.vdms_retriever.retriever.VDMS')
    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    @patch('src.vdms_retriever.retriever.client')
    def test_get_vectordb_empty_string_settings(self, mock_client, mock_settings, mock_embedding_wrapper, mock_vdms):
        """Test get_vectordb with empty string settings."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup mock settings with empty strings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = ""
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = ""
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 1
        mock_settings.INDEX_NAME = ""
        mock_settings.DISTANCE_STRATEGY = ""
        mock_settings.SEARCH_ENGINE = ""

        # Setup mock embedding wrapper
        mock_embedding_instance = Mock()
        mock_embedding_instance.get_embedding_length.return_value = 128
        mock_embedding_wrapper.return_value = mock_embedding_instance

        # Setup mock VDMS
        mock_vdms_instance = Mock()
        mock_vdms.return_value = mock_vdms_instance

        # Call the function
        result = get_vectordb()

        # Verify embedding wrapper was created with empty strings
        mock_embedding_wrapper.assert_called_once_with(
            api_url="",
            model_name="",
            num_frames=1
        )

        # Verify VDMS was initialized with empty strings
        mock_vdms.assert_called_once_with(
            client=mock_client,
            embedding=mock_embedding_instance,
            collection_name="",
            embedding_dimensions=128,
            distance_strategy="",
            engine=""
        )

        assert result == mock_vdms_instance

    def test_module_imports(self):
        """Test that all required modules are imported correctly."""
        from src.vdms_retriever.retriever import get_vectordb
        from src.vdms_retriever.embedding_wrapper import vCLIPEmbeddingsWrapper
        
        # Test that get_vectordb function is callable
        assert callable(get_vectordb)
        
        # Test that vCLIPEmbeddingsWrapper is available
        assert vCLIPEmbeddingsWrapper is not None

    @patch('src.vdms_retriever.retriever.VDMS')
    @patch('src.vdms_retriever.retriever.vCLIPEmbeddingsWrapper')
    @patch('src.vdms_retriever.retriever.settings')
    @patch('src.vdms_retriever.retriever.client')
    def test_get_vectordb_integration_flow(self, mock_client, mock_settings, mock_embedding_wrapper, mock_vdms):
        """Test the complete integration flow of get_vectordb."""
        from src.vdms_retriever.retriever import get_vectordb
        
        # Setup mock settings
        mock_settings.VCLIP_EMBEDDINGS_ENDPOINT = "http://localhost:8080/embeddings"
        mock_settings.VCLIP_EMBEDDINGS_MODEL_NAME = "vclip-model"
        mock_settings.VCLIP_EMBEDDINGS_NUM_FRAMES = 8
        mock_settings.INDEX_NAME = "integration_test"
        mock_settings.DISTANCE_STRATEGY = "cosine"
        mock_settings.SEARCH_ENGINE = "faiss"

        # Setup mock embedding wrapper
        mock_embedding_instance = Mock()
        mock_embedding_instance.get_embedding_length.return_value = 768
        mock_embedding_wrapper.return_value = mock_embedding_instance

        # Setup mock VDMS
        mock_vdms_instance = Mock()
        mock_vdms.return_value = mock_vdms_instance

        # Call the function
        result = get_vectordb()

        # Verify the complete flow
        assert mock_embedding_wrapper.call_count == 1
        assert mock_embedding_instance.get_embedding_length.call_count == 1
        assert mock_vdms.call_count == 1
        assert result == mock_vdms_instance