"""Semantic matching using VLM."""

import logging
import time
from typing import Optional

from app.core.config import settings
from app.core.metrics import matches_total, vlm_inference_duration_seconds
from app.services.matchers.base import BaseMatcher, MatchResult
from app.services.vlm.base import BaseVLMBackend
from app.services.vlm.factory import VLMBackendFactory
from app.utils.cache import cache

logger = logging.getLogger(__name__)


SEMANTIC_PROMPT_TEMPLATE = """You are matching product names in a {context} context.

Expected product: "{expected}"
Detected product: "{detected}"

Question:
Could these refer to the same real-world product, even if one name is shorter, simplified, or missing adjectives/descriptors?

Rules:
- Focus on the core product identity, not exact wording
- "green apple" and "apple" -> YES (same product family)
- "cola" and "coca cola bottle" -> YES (same product type)
- "bread" and "milk" -> NO (different products)
- "small bottle" and "large bottle" of same item -> YES (same product, different size)

Answer ONLY with YES or NO, nothing else.
"""


class SemanticMatcher(BaseMatcher):
    """Semantic matching using VLM backend."""
    
    def __init__(
        self,
        vlm_backend: Optional[BaseVLMBackend] = None,
        confidence_threshold: float = 0.85,
        use_cache: bool = True,
    ):
        """
        Initialize semantic matcher.
        
        Args:
            vlm_backend: VLM backend instance (auto-created if None)
            confidence_threshold: Minimum confidence for positive match
            use_cache: Enable caching of results
        """
        self.vlm_backend = vlm_backend or VLMBackendFactory.create(settings.vlm_backend)
        self.confidence_threshold = confidence_threshold
        self.use_cache = use_cache
    
    @property
    def name(self) -> str:
        """Get matcher name."""
        return "semantic"
    
    async def match(
        self,
        text1: str,
        text2: str,
        context: str = "grocery products",
    ) -> MatchResult:
        """
        Perform semantic matching using VLM.
        
        Args:
            text1: First text (expected)
            text2: Second text (detected)
            context: Context for matching (e.g., "grocery products")
        
        Returns:
            MatchResult with VLM-based confidence
        """
        if not text1 or not text2:
            return MatchResult(
                match=False,
                confidence=0.0,
                reasoning="One or both inputs are empty",
                match_type="semantic",
            )
        
        # Check cache
        cache_key = None
        if self.use_cache:
            cache_key = cache.make_key("semantic", text1, text2, context)
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for semantic match: '{text1}' vs '{text2}'")
                return MatchResult(**cached_result)
        
        # Check VLM backend availability
        if not self.vlm_backend.is_available():
            logger.error("VLM backend not available")
            return MatchResult(
                match=False,
                confidence=0.0,
                reasoning="VLM backend not available",
                match_type="semantic",
            )
        
        # Generate prompt
        prompt = SEMANTIC_PROMPT_TEMPLATE.format(
            context=context,
            expected=text1,
            detected=text2,
        )
        
        logger.info(f"Semantic match: '{text1}' ↔ '{text2}' (context: {context})")
        
        # Call VLM
        start_time = time.time()
        try:
            response = await self.vlm_backend.generate_text(
                prompt=prompt,
                max_tokens=10,
                temperature=0.0,
            )
            
            inference_time = time.time() - start_time
            vlm_inference_duration_seconds.labels(backend=settings.vlm_backend).observe(inference_time)
            
            # Parse response
            answer = response.strip().upper()
            is_match = answer.startswith("YES")
            
            # Assign confidence based on response clarity
            if "YES" in answer:
                confidence = 0.95
            elif "NO" in answer:
                confidence = 0.05
            else:
                # Ambiguous response
                confidence = 0.5
                logger.warning(f"Ambiguous VLM response: '{response}'")
            
            reasoning = f"VLM response: {answer} (inference_time={inference_time:.3f}s)"
            
            result = MatchResult(
                match=is_match and confidence >= self.confidence_threshold,
                confidence=confidence,
                reasoning=reasoning,
                match_type="semantic",
            )
            
            # Cache result
            if self.use_cache and cache_key:
                await cache.set(
                    cache_key,
                    {
                        "match": result.match,
                        "confidence": result.confidence,
                        "reasoning": result.reasoning,
                        "match_type": result.match_type,
                    },
                    ttl=settings.cache_ttl,
                )
            
            # Update metrics
            matches_total.labels(
                match_type="semantic",
                result="match" if result.match else "no_match",
            ).inc()
            
            logger.info(f"Semantic match result: {result.match} (confidence={result.confidence:.2f})")
            
            return result
        
        except Exception as e:
            logger.error(f"VLM inference failed: {e}", exc_info=True)
            return MatchResult(
                match=False,
                confidence=0.0,
                reasoning=f"VLM inference error: {str(e)}",
                match_type="semantic",
            )
