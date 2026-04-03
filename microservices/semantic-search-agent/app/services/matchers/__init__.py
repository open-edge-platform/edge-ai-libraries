"""Matcher factory."""

from typing import Literal

from app.services.matchers.base import BaseMatcher
from app.services.matchers.exact import ExactMatcher
from app.services.matchers.hybrid import HybridMatcher
from app.services.matchers.semantic import SemanticMatcher


class MatcherFactory:
    """Factory for creating matcher instances."""
    
    @staticmethod
    def create(
        strategy: Literal["exact", "semantic", "hybrid"] = "hybrid"
    ) -> BaseMatcher:
        """
        Create matcher instance based on strategy.
        
        Args:
            strategy: Matching strategy (exact, semantic, hybrid)
        
        Returns:
            BaseMatcher instance
        """
        if strategy == "exact":
            return ExactMatcher()
        elif strategy == "semantic":
            return SemanticMatcher()
        elif strategy == "hybrid":
            return HybridMatcher()
        else:
            raise ValueError(f"Unknown matching strategy: {strategy}")
