"""Exact string matching strategy."""

import logging
from typing import Optional

from app.services.matchers.base import BaseMatcher, MatchResult
from app.utils import normalize_text, remove_special_chars, similarity_ratio

logger = logging.getLogger(__name__)


class ExactMatcher(BaseMatcher):
    """Exact string matching with normalization."""
    
    def __init__(
        self,
        case_insensitive: bool = True,
        strip_whitespace: bool = True,
        normalize_special_chars: bool = True,
    ):
        """
        Initialize exact matcher.
        
        Args:
            case_insensitive: Perform case-insensitive comparison
            strip_whitespace: Strip whitespace before comparison
            normalize_special_chars: Remove special characters
        """
        self.case_insensitive = case_insensitive
        self.strip_whitespace = strip_whitespace
        self.normalize_special_chars = normalize_special_chars
    
    @property
    def name(self) -> str:
        """Get matcher name."""
        return "exact"
    
    async def match(
        self,
        text1: str,
        text2: str,
        context: str = "",
    ) -> MatchResult:
        """
        Perform exact string matching with normalization.
        
        Returns:
            MatchResult with 1.0 confidence if exact match, 0.0 otherwise
        """
        if not text1 or not text2:
            return MatchResult(
                match=False,
                confidence=0.0,
                reasoning="One or both inputs are empty",
                match_type="exact",
            )
        
        # Normalize both texts
        normalized1 = normalize_text(
            text1,
            lowercase=self.case_insensitive,
            strip_whitespace=self.strip_whitespace,
        )
        normalized2 = normalize_text(
            text2,
            lowercase=self.case_insensitive,
            strip_whitespace=self.strip_whitespace,
        )
        
        if self.normalize_special_chars:
            normalized1 = remove_special_chars(normalized1)
            normalized2 = remove_special_chars(normalized2)
        
        # Check exact match
        is_match = normalized1 == normalized2
        
        # If not exact match, calculate similarity for partial confidence
        confidence = 1.0 if is_match else 0.0
        
        # For near matches, provide partial confidence
        if not is_match:
            sim_ratio = similarity_ratio(text1, text2)
            if sim_ratio > 0.9:
                confidence = sim_ratio
        
        reasoning = (
            f"Exact match after normalization"
            if is_match
            else f"No exact match (normalized: '{normalized1}' != '{normalized2}')"
        )
        
        logger.debug(
            f"Exact match: '{text1}' vs '{text2}' -> {is_match} (confidence={confidence:.2f})"
        )
        
        return MatchResult(
            match=is_match,
            confidence=confidence,
            reasoning=reasoning,
            match_type="exact",
        )
