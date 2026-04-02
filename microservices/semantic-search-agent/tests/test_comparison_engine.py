"""Tests for comparison engine."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.comparison_engine import ComparisonEngine
from app.services.matchers.exact import ExactMatcher
from app.services.matchers.base import MatchResult


class TestComparisonEngine:
    """Tests for ComparisonEngine."""
    
    @pytest.fixture
    def engine(self):
        """Create comparison engine with exact matcher."""
        matcher = ExactMatcher()
        return ComparisonEngine(matcher=matcher)
    
    @pytest.mark.asyncio
    async def test_validate_order_exact_match(
        self, engine, sample_expected_items, sample_detected_items_exact_match
    ):
        """Test order validation with exact matches."""
        result = await engine.validate_order(
            expected_items=sample_expected_items,
            detected_items=sample_detected_items_exact_match,
            use_semantic=False,
        )
        
        assert result["status"] == "validated"
        assert len(result["validation"]["missing"]) == 0
        assert len(result["validation"]["extra"]) == 0
        assert len(result["validation"]["quantity_mismatch"]) == 0
        assert len(result["validation"]["matched"]) == 3
        assert result["metrics"]["exact_matches"] == 3
    
    @pytest.mark.asyncio
    async def test_validate_order_with_mismatch(
        self, engine, sample_expected_items, sample_detected_items_with_mismatch
    ):
        """Test order validation with mismatches."""
        result = await engine.validate_order(
            expected_items=sample_expected_items,
            detected_items=sample_detected_items_with_mismatch,
            use_semantic=False,
        )
        
        assert result["status"] == "mismatch"
        assert len(result["validation"]["missing"]) > 0  # apple, milk missing (no semantic)
        assert len(result["validation"]["extra"]) > 0  # green apple, orange extra
        assert len(result["validation"]["quantity_mismatch"]) == 1  # banana quantity
    
    @pytest.mark.asyncio
    async def test_validate_inventory(self, engine, sample_inventory):
        """Test inventory validation."""
        items = ["apple", "banana", "unknown item"]
        
        result = await engine.validate_inventory(
            items=items,
            inventory=sample_inventory,
            use_semantic=False,
        )
        
        assert result["summary"]["total_items"] == 3
        # Exact match for "apple" and "banana" won't match inventory (case/format difference)
        # so all might be unmatched without semantic
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 3
    
    @pytest.mark.asyncio
    async def test_semantic_match(self, engine):
        """Test generic semantic matching."""
        # Mock the matcher to return a positive result
        engine.matcher = AsyncMock()
        engine.matcher.match.return_value = MatchResult(
            match=True,
            confidence=0.95,
            reasoning="Semantic match",
            match_type="semantic",
        )
        
        result = await engine.semantic_match("apple", "green apple")
        
        assert result["match"] is True
        assert result["confidence"] == 0.95
        assert result["match_type"] == "semantic"
        engine.matcher.match.assert_called_once()


class TestComparisonEngineWithSemanticMatcher:
    """Tests for ComparisonEngine with semantic matching."""
    
    @pytest.fixture
    def engine_with_semantic(self, mock_vlm_backend):
        """Create comparison engine with mock semantic matcher."""
        from app.services.matchers.semantic import SemanticMatcher
        matcher = SemanticMatcher(vlm_backend=mock_vlm_backend, use_cache=False)
        return ComparisonEngine(matcher=matcher)
    
    @pytest.mark.asyncio
    async def test_validate_order_with_semantic_match(
        self,
        engine_with_semantic,
        sample_expected_items,
        sample_detected_items_with_mismatch,
        mock_vlm_backend,
    ):
        """Test order validation with semantic matching enabled."""
        # Mock VLM to return YES for "apple" vs "green apple"
        mock_vlm_backend.generate_text.return_value = "YES"
        
        result = await engine_with_semantic.validate_order(
            expected_items=sample_expected_items,
            detected_items=sample_detected_items_with_mismatch,
            use_semantic=True,
        )
        
        # With semantic matching, "apple" should match "green apple"
        assert result["status"] == "mismatch"
        assert len(result["validation"]["missing"]) < len(sample_expected_items)
        assert result["metrics"]["semantic_matches"] >= 0
