"""Base matcher interface and result models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class MatchResult:
    """Result of a matching operation."""
    
    match: bool
    confidence: float
    reasoning: str = ""
    match_type: str = "unknown"
    
    def __post_init__(self):
        """Validate confidence score."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0 and 1, got {self.confidence}")


class BaseMatcher(ABC):
    """Abstract base class for all matchers."""
    
    @abstractmethod
    async def match(
        self,
        text1: str,
        text2: str,
        context: str = "",
    ) -> MatchResult:
        """
        Compare two text strings and return match result.
        
        Args:
            text1: First text to compare
            text2: Second text to compare
            context: Optional context for matching (e.g., "grocery products")
        
        Returns:
            MatchResult with match status, confidence, and reasoning
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get matcher name."""
        pass
