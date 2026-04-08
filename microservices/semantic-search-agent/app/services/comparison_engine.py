"""Comparison engine for order and inventory validation."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.metrics import matches_total, request_duration_seconds
from app.services.matchers import MatcherFactory
from app.services.matchers.base import BaseMatcher
from app.utils import normalize_text

logger = logging.getLogger(__name__)


class ComparisonEngine:
    """Core comparison engine for order and inventory validation."""
    
    def __init__(self, matcher: Optional[BaseMatcher] = None):
        """
        Initialize comparison engine.
        
        Args:
            matcher: Matcher instance (auto-created if None)
        """
        self.matcher = matcher or MatcherFactory.create(settings.default_matching_strategy)
        self._orders_cache: Optional[Dict] = None
        self._inventory_cache: Optional[List[str]] = None
    
    def _load_orders(self) -> Dict:
        """Load orders from JSON file."""
        if self._orders_cache is None:
            if settings.orders_file.exists():
                with open(settings.orders_file, "r") as f:
                    self._orders_cache = json.load(f)
                logger.info(f"Loaded {len(self._orders_cache)} orders from config")
            else:
                logger.warning(f"Orders file not found: {settings.orders_file}")
                self._orders_cache = {}
        
        return self._orders_cache
    
    def _load_inventory(self) -> List[str]:
        """Load inventory from JSON file."""
        if self._inventory_cache is None:
            if settings.inventory_file.exists():
                with open(settings.inventory_file, "r") as f:
                    self._inventory_cache = json.load(f)
                logger.info(f"Loaded {len(self._inventory_cache)} inventory items from config")
            else:
                logger.warning(f"Inventory file not found: {settings.inventory_file}")
                self._inventory_cache = []
        
        return self._inventory_cache
    
    async def validate_order(
        self,
        expected_items: List[Dict[str, any]],
        detected_items: List[Dict[str, any]],
        use_semantic: bool = True,
        exact_match_first: bool = True,
    ) -> Dict:
        """
        Validate order by comparing expected vs detected items.
        
        Args:
            expected_items: List of expected items with name and quantity
            detected_items: List of detected items with name and quantity
            use_semantic: Enable semantic matching
            exact_match_first: Try exact match before semantic
        
        Returns:
            Dictionary with validation results (missing, extra, quantity_mismatch, matched)
        """
        start_time = time.time()
        
        missing = []
        extra = []
        quantity_mismatch = []
        matched = []
        matched_detected = set()
        
        logger.info(
            f"Validating order: {len(expected_items)} expected, {len(detected_items)} detected"
        )
        
        # Pass 1: Exact matching
        for exp in expected_items:
            exp_name = normalize_text(exp["name"])
            exp_qty = exp["quantity"]
            found = False
            
            for det in detected_items:
                det_name = normalize_text(det["name"])
                det_qty = det["quantity"]
                
                if det_name == exp_name:
                    found = True
                    matched_detected.add(det_name)
                    
                    matched.append({
                        "expected": exp,
                        "detected": det,
                        "match_type": "exact",
                        "confidence": 1.0,
                    })
                    
                    if det_qty != exp_qty:
                        quantity_mismatch.append({
                            "name": exp_name,
                            "expected": exp_qty,
                            "detected": det_qty,
                        })
                    break
            
            if not found:
                missing.append(exp)
        
        # Pass 2: Semantic matching (if enabled)
        if use_semantic and missing:
            still_missing = []
            
            for exp in missing:
                exp_name = exp["name"]
                exp_qty = exp["quantity"]
                matched_item = False
                
                for det in detected_items:
                    det_name = det["name"]
                    det_norm = normalize_text(det_name)
                    
                    if det_norm in matched_detected:
                        continue
                    
                    # Semantic match
                    match_result = await self.matcher.match(exp_name, det_name)
                    
                    if match_result.match:
                        matched_item = True
                        matched_detected.add(det_norm)
                        
                        matched.append({
                            "expected": exp,
                            "detected": det,
                            "match_type": match_result.match_type,
                            "confidence": match_result.confidence,
                        })
                        
                        if det["quantity"] != exp_qty:
                            quantity_mismatch.append({
                                "name": exp_name,
                                "expected": exp_qty,
                                "detected": det["quantity"],
                            })
                        break
                
                if not matched_item:
                    still_missing.append(exp)
            
            missing = still_missing
        
        # Find extra items
        for det in detected_items:
            det_norm = normalize_text(det["name"])
            if det_norm not in matched_detected:
                extra.append(det)
        
        processing_time = (time.time() - start_time) * 1000
        
        result = {
            "status": "validated" if not (missing or extra or quantity_mismatch) else "mismatch",
            "validation": {
                "missing": missing,
                "extra": extra,
                "quantity_mismatch": quantity_mismatch,
                "matched": matched,
            },
            "metrics": {
                "total_expected": len(expected_items),
                "total_detected": len(detected_items),
                "exact_matches": sum(1 for m in matched if m["match_type"] == "exact"),
                "semantic_matches": sum(1 for m in matched if "semantic" in m["match_type"]),
                "processing_time_ms": round(processing_time, 2),
            },
        }
        
        logger.info(
            f"Order validation complete: {result['status']} "
            f"(matched={len(matched)}, missing={len(missing)}, extra={len(extra)})"
        )
        
        return result
    
    async def validate_inventory(
        self,
        items: List[str],
        inventory: Optional[List[str]] = None,
        use_semantic: bool = True,
    ) -> Dict:
        """
        Validate if items exist in inventory.
        
        Args:
            items: List of item names to validate
            inventory: Inventory list (loads from config if None)
            use_semantic: Enable semantic matching
        
        Returns:
            Dictionary with validation results for each item
        """
        start_time = time.time()
        
        if inventory is None:
            inventory = self._load_inventory()
        
        logger.info(f"Validating {len(items)} items against inventory of {len(inventory)}")
        
        results = []
        
        for item in items:
            item_norm = normalize_text(item)
            matched = False
            matched_item = None
            match_type = None
            confidence = 0.0
            
            # Try exact match first
            for inv_item in inventory:
                if normalize_text(inv_item) == item_norm:
                    matched = True
                    matched_item = inv_item
                    match_type = "exact"
                    confidence = 1.0
                    break
            
            # Try semantic match if no exact match and semantic enabled
            if not matched and use_semantic:
                for inv_item in inventory:
                    match_result = await self.matcher.match(item, inv_item)
                    
                    if match_result.match and match_result.confidence > confidence:
                        matched = True
                        matched_item = inv_item
                        match_type = match_result.match_type
                        confidence = match_result.confidence
            
            results.append({
                "item": item,
                "match": matched,
                "matched_inventory_item": matched_item,
                "match_type": match_type,
                "confidence": confidence,
            })
            
            # Update metrics
            matches_total.labels(
                match_type=match_type or "none",
                result="match" if matched else "no_match",
            ).inc()
        
        processing_time = (time.time() - start_time) * 1000
        
        summary = {
            "results": results,
            "summary": {
                "total_items": len(items),
                "matched": sum(1 for r in results if r["match"]),
                "unmatched": sum(1 for r in results if not r["match"]),
                "processing_time_ms": round(processing_time, 2),
            },
        }
        
        logger.info(
            f"Inventory validation complete: "
            f"{summary['summary']['matched']}/{len(items)} matched"
        )
        
        return summary
    
    async def semantic_match(
        self,
        text1: str,
        text2: str,
        context: str = "grocery products",
    ) -> Dict:
        """
        Perform generic semantic matching.
        
        Args:
            text1: First text to compare
            text2: Second text to compare
            context: Context for matching
        
        Returns:
            Dictionary with match result
        """
        start_time = time.time()
        
        logger.info(f"Semantic match: '{text1}' ↔ '{text2}'")
        
        match_result = await self.matcher.match(text1, text2, context)
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "match": match_result.match,
            "confidence": match_result.confidence,
            "reasoning": match_result.reasoning,
            "match_type": match_result.match_type,
            "processing_time_ms": round(processing_time, 2),
        }
