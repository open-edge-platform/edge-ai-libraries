"""Pydantic models for API requests and responses."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# Request models

class ItemModel(BaseModel):
    """Item with name and quantity."""
    name: str = Field(..., description="Item name")
    quantity: int = Field(..., ge=1, description="Item quantity")


class ComparisonOptions(BaseModel):
    """Options for comparison."""
    use_semantic: bool = Field(default=True, description="Enable semantic matching")
    exact_match_first: bool = Field(default=True, description="Try exact match before semantic")
    case_insensitive: bool = Field(default=True, description="Case-insensitive comparison")


class OrderValidationRequest(BaseModel):
    """Request model for order validation."""
    expected_items: List[ItemModel] = Field(..., description="Expected items")
    detected_items: List[ItemModel] = Field(..., description="Detected items")
    options: Optional[ComparisonOptions] = Field(default=None, description="Comparison options")


class InventoryValidationRequest(BaseModel):
    """Request model for inventory validation."""
    items: List[str] = Field(..., description="Items to validate")
    inventory: Optional[List[str]] = Field(default=None, description="Inventory list (uses config if null)")
    options: Optional[ComparisonOptions] = Field(default=None, description="Comparison options")


class SemanticMatchRequest(BaseModel):
    """Request model for semantic matching."""
    text1: str = Field(..., description="First text to compare")
    text2: str = Field(..., description="Second text to compare")
    context: str = Field(default="grocery products", description="Context for matching")


# Response models

class MatchedItemModel(BaseModel):
    """Matched item pair."""
    expected: ItemModel
    detected: ItemModel
    match_type: str
    confidence: float


class QuantityMismatchModel(BaseModel):
    """Quantity mismatch info."""
    name: str
    expected: int
    detected: int


class OrderValidationResult(BaseModel):
    """Result of order validation."""
    missing: List[ItemModel]
    extra: List[ItemModel]
    quantity_mismatch: List[QuantityMismatchModel]
    matched: List[MatchedItemModel]


class OrderValidationMetrics(BaseModel):
    """Metrics for order validation."""
    total_expected: int
    total_detected: int
    exact_matches: int
    semantic_matches: int
    processing_time_ms: float


class OrderValidationResponse(BaseModel):
    """Response model for order validation."""
    status: Literal["validated", "mismatch"]
    validation: OrderValidationResult
    metrics: OrderValidationMetrics


class InventoryItemResult(BaseModel):
    """Result for single inventory item."""
    item: str
    match: bool
    matched_inventory_item: Optional[str]
    match_type: Optional[str]
    confidence: float


class InventoryValidationSummary(BaseModel):
    """Summary of inventory validation."""
    total_items: int
    matched: int
    unmatched: int
    processing_time_ms: float


class InventoryValidationResponse(BaseModel):
    """Response model for inventory validation."""
    results: List[InventoryItemResult]
    summary: InventoryValidationSummary


class SemanticMatchResponse(BaseModel):
    """Response model for semantic matching."""
    match: bool
    confidence: float
    reasoning: str
    match_type: str
    processing_time_ms: float


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    vlm_backend: str
    vlm_status: str
    uptime_seconds: float
