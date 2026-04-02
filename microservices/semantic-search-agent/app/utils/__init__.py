"""Utility functions for text processing."""

import re
import unicodedata
from typing import Optional


def normalize_text(text: str, lowercase: bool = True, strip_whitespace: bool = True) -> str:
    """
    Normalize text for comparison.
    
    Args:
        text: Input text to normalize
        lowercase: Convert to lowercase
        strip_whitespace: Strip leading/trailing whitespace
    
    Returns:
        Normalized text
    """
    if not text:
        return ""
    
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", text)
    
    # Remove accents
    text = "".join([c for c in text if not unicodedata.combining(c)])
    
    if lowercase:
        text = text.lower()
    
    if strip_whitespace:
        text = text.strip()
        # Replace multiple spaces with single space
        text = re.sub(r"\s+", " ", text)
    
    return text


def remove_special_chars(text: str, keep_spaces: bool = True) -> str:
    """
    Remove special characters from text.
    
    Args:
        text: Input text
        keep_spaces: Keep space characters
    
    Returns:
        Text with special characters removed
    """
    if keep_spaces:
        return re.sub(r"[^a-zA-Z0-9\s]", "", text)
    return re.sub(r"[^a-zA-Z0-9]", "", text)


def extract_numbers(text: str) -> list[int]:
    """Extract all numbers from text."""
    return [int(n) for n in re.findall(r"\d+", text)]


def similarity_ratio(text1: str, text2: str) -> float:
    """
    Calculate simple character-based similarity ratio.
    
    Returns:
        Similarity score between 0 and 1
    """
    text1 = normalize_text(text1)
    text2 = normalize_text(text2)
    
    if not text1 or not text2:
        return 0.0
    
    # Simple character overlap ratio
    set1 = set(text1.split())
    set2 = set(text2.split())
    
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0
