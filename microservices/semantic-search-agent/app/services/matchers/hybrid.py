"""Hybrid matcher combining exact and semantic strategies."""

import logging
from typing import Optional

from app.services.matchers.base import BaseMatcher, MatchResult
from app.services.matchers.exact import ExactMatcher
from app.services.matchers.semantic import SemanticMatcher

logger = logging.getLogger(__name__)


class HybridMatcher(BaseMatcher):
    """Hybrid matcher: tries exact match first, falls back to semantic."""
    
    def __init__(
        self,
        exact_matcher: Optional[ExactMatcher] = None,
        semantic_matcher: Optional[SemanticMatcher] = None,
        exact_confidence_threshold: float = 0.9,
    ):
        """
        Initialize hybrid matcher.
        
        Args:
            exact_matcher: Exact matcher instance
            semantic_matcher: Semantic matcher instance
            exact_confidence_threshold: Minimum confidence to skip semantic matching
        """
        self.exact_matcher = exact_matcher or ExactMatcher()
        self.semantic_matcher = semantic_matcher or SemanticMatcher()
        self.exact_confidence_threshold = exact_confidence_threshold
    
    @property
    def name(self) -> str:
        """Get matcher name."""
        return "hybrid"
    
    async def match(
        self,
        text1: str,
        text2: str,
        context: str = "",
    ) -> MatchResult:
        """
        Perform hybrid matching: exact first, then semantic.
        
        Strategy:
        1. Try exact match
        2. If exact confidence >= threshold, return exact result
        3. Otherwise, try semantic match
        4. Return best result based on confidence
        
        Returns:
            MatchResult from exact or semantic matcher
        """
        if not text1 or not text2:
            return MatchResult(
                match=False,
                confidence=0.0,
                reasoning="One or both inputs are empty",
                match_type="hybrid",
            )
        
        logger.debug(f"Hybrid match: '{text1}' vs '{text2}'")
        
        # Try exact match first (fast path)
        exact_result = await self.exact_matcher.match(text1, text2, context)
        
        if exact_result.confidence >= self.exact_confidence_threshold:
            logger.debug(
                f"Exact match succeeded with high confidence: {exact_result.confidence:.2f}"
            )
            return MatchResult(
                match=exact_result.match,
                confidence=exact_result.confidence,
                reasoning=f"Exact match (confidence={exact_result.confidence:.2f})",
                match_type="hybrid_exact",
            )
        
        # Exact match failed or low confidence, try semantic
        logger.debug("Exact match confidence too low, trying semantic match")
        semantic_result = await self.semantic_matcher.match(text1, text2, context)
        
        # Return semantic result with hybrid match type
        return MatchResult(
            match=semantic_result.match,
            confidence=semantic_result.confidence,
            reasoning=(
                f"Hybrid: Exact={exact_result.confidence:.2f}, "
                f"Semantic={semantic_result.confidence:.2f} -> {semantic_result.reasoning}"
            ),
            match_type="hybrid_semantic",
        )
