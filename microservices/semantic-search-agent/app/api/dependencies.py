"""Dependency injection for API routes."""

from functools import lru_cache

from app.services.comparison_engine import ComparisonEngine


@lru_cache()
def get_comparison_engine() -> ComparisonEngine:
    """Get cached comparison engine instance."""
    return ComparisonEngine()
