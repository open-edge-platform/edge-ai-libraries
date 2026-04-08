"""Tests for matcher strategies."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.matchers.exact import ExactMatcher
from app.services.matchers.semantic import SemanticMatcher
from app.services.matchers.hybrid import HybridMatcher
from app.services.matchers.base import MatchResult


class TestExactMatcher:
    """Tests for ExactMatcher."""
    
    @pytest.fixture
    def matcher(self):
        """Create exact matcher instance."""
        return ExactMatcher()
    
    @pytest.mark.asyncio
    async def test_exact_match(self, matcher):
        """Test exact string match."""
        result = await matcher.match("apple", "apple")
        assert result.match is True
        assert result.confidence == 1.0
        assert result.match_type == "exact"
    
    @pytest.mark.asyncio
    async def test_case_insensitive_match(self, matcher):
        """Test case-insensitive matching."""
        result = await matcher.match("Apple", "apple")
        assert result.match is True
        assert result.confidence == 1.0
    
    @pytest.mark.asyncio
    async def test_whitespace_normalization(self, matcher):
        """Test whitespace normalization."""
        result = await matcher.match("  apple  ", "apple")
        assert result.match is True
        assert result.confidence == 1.0
    
    @pytest.mark.asyncio
    async def test_no_match(self, matcher):
        """Test no match."""
        result = await matcher.match("apple", "banana")
        assert result.match is False
        assert result.confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_empty_input(self, matcher):
        """Test empty input."""
        result = await matcher.match("", "apple")
        assert result.match is False
        assert result.confidence == 0.0


class TestSemanticMatcher:
    """Tests for SemanticMatcher."""
    
    @pytest.fixture
    def matcher(self, mock_vlm_backend):
        """Create semantic matcher with mock VLM."""
        return SemanticMatcher(vlm_backend=mock_vlm_backend, use_cache=False)
    
    @pytest.mark.asyncio
    async def test_semantic_match_yes(self, matcher, mock_vlm_backend):
        """Test semantic match returning YES."""
        mock_vlm_backend.generate_text.return_value = "YES"
        
        result = await matcher.match("apple", "green apple")
        
        assert result.match is True
        assert result.confidence == 0.95
        assert result.match_type == "semantic"
        mock_vlm_backend.generate_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_semantic_match_no(self, matcher, mock_vlm_backend):
        """Test semantic match returning NO."""
        mock_vlm_backend.generate_text.return_value = "NO"
        
        result = await matcher.match("apple", "banana")
        
        assert result.match is False
        assert result.confidence == 0.05
        mock_vlm_backend.generate_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_vlm_unavailable(self, matcher, mock_vlm_backend):
        """Test VLM backend unavailable."""
        mock_vlm_backend.is_available.return_value = False
        
        result = await matcher.match("apple", "green apple")
        
        assert result.match is False
        assert result.confidence == 0.0
        assert "not available" in result.reasoning
    
    @pytest.mark.asyncio
    async def test_vlm_error(self, matcher, mock_vlm_backend):
        """Test VLM inference error."""
        mock_vlm_backend.generate_text.side_effect = Exception("VLM error")
        
        result = await matcher.match("apple", "green apple")
        
        assert result.match is False
        assert result.confidence == 0.0
        assert "error" in result.reasoning.lower()


class TestHybridMatcher:
    """Tests for HybridMatcher."""
    
    @pytest.fixture
    def matcher(self, mock_vlm_backend):
        """Create hybrid matcher."""
        exact_matcher = ExactMatcher()
        semantic_matcher = SemanticMatcher(vlm_backend=mock_vlm_backend, use_cache=False)
        return HybridMatcher(exact_matcher=exact_matcher, semantic_matcher=semantic_matcher)
    
    @pytest.mark.asyncio
    async def test_exact_match_short_circuits(self, matcher, mock_vlm_backend):
        """Test that exact match short-circuits semantic matching."""
        result = await matcher.match("apple", "apple")
        
        assert result.match is True
        assert result.confidence == 1.0
        assert "exact" in result.match_type
        # VLM should not be called
        mock_vlm_backend.generate_text.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_falls_back_to_semantic(self, matcher, mock_vlm_backend):
        """Test fallback to semantic matching."""
        mock_vlm_backend.generate_text.return_value = "YES"
        
        result = await matcher.match("apple", "green apple")
        
        assert result.match is True
        assert "semantic" in result.match_type
        # VLM should be called
        mock_vlm_backend.generate_text.assert_called_once()
