"""Tests for text utilities."""

import pytest

from app.utils import (
    normalize_text,
    remove_special_chars,
    extract_numbers,
    similarity_ratio,
)


class TestNormalizeText:
    """Tests for normalize_text function."""
    
    def test_lowercase(self):
        """Test lowercase conversion."""
        assert normalize_text("APPLE", lowercase=True) == "apple"
        assert normalize_text("Apple", lowercase=True) == "apple"
    
    def test_strip_whitespace(self):
        """Test whitespace stripping."""
        assert normalize_text("  apple  ", strip_whitespace=True) == "apple"
        assert normalize_text("apple  banana", strip_whitespace=True) == "apple banana"
    
    def test_multiple_spaces(self):
        """Test multiple space normalization."""
        assert normalize_text("apple    banana", strip_whitespace=True) == "apple banana"
    
    def test_unicode_normalization(self):
        """Test unicode character normalization."""
        assert normalize_text("café") == "cafe"
        assert normalize_text("naïve") == "naive"
    
    def test_combined(self):
        """Test combined normalization."""
        result = normalize_text("  CAFÉ  ", lowercase=True, strip_whitespace=True)
        assert result == "cafe"


class TestRemoveSpecialChars:
    """Tests for remove_special_chars function."""
    
    def test_remove_punctuation(self):
        """Test punctuation removal."""
        assert remove_special_chars("apple,banana!", keep_spaces=False) == "applebanana"
    
    def test_keep_spaces(self):
        """Test keeping spaces."""
        assert remove_special_chars("apple banana!", keep_spaces=True) == "apple banana"
    
    def test_numbers_preserved(self):
        """Test that numbers are preserved."""
        assert remove_special_chars("item123", keep_spaces=False) == "item123"


class TestExtractNumbers:
    """Tests for extract_numbers function."""
    
    def test_single_number(self):
        """Test extracting single number."""
        assert extract_numbers("apple 2") == [2]
    
    def test_multiple_numbers(self):
        """Test extracting multiple numbers."""
        assert extract_numbers("2 apples and 3 bananas") == [2, 3]
    
    def test_no_numbers(self):
        """Test no numbers."""
        assert extract_numbers("apple banana") == []


class TestSimilarityRatio:
    """Tests for similarity_ratio function."""
    
    def test_identical_strings(self):
        """Test identical strings."""
        assert similarity_ratio("apple", "apple") == 1.0
    
    def test_completely_different(self):
        """Test completely different strings."""
        assert similarity_ratio("apple", "banana") == 0.0
    
    def test_partial_overlap(self):
        """Test partial overlap."""
        ratio = similarity_ratio("green apple", "apple red")
        assert 0.0 < ratio < 1.0
    
    def test_empty_strings(self):
        """Test empty strings."""
        assert similarity_ratio("", "apple") == 0.0
        assert similarity_ratio("apple", "") == 0.0
