"""Integration tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    def test_health_check_success(self, client):
        """Test successful health check."""
        with patch("app.api.routes.VLMBackendFactory.create") as mock_factory:
            mock_backend = MagicMock()
            mock_backend.is_available.return_value = True
            mock_factory.return_value = mock_backend
            
            response = client.get("/api/v1/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "version" in data
            assert "vlm_backend" in data


class TestOrderValidationEndpoint:
    """Tests for order validation endpoint."""
    
    def test_order_validation_success(self, client):
        """Test successful order validation."""
        payload = {
            "expected_items": [
                {"name": "apple", "quantity": 2},
                {"name": "banana", "quantity": 1},
            ],
            "detected_items": [
                {"name": "apple", "quantity": 2},
                {"name": "banana", "quantity": 1},
            ],
            "options": {
                "use_semantic": False,
                "exact_match_first": True,
            },
        }
        
        response = client.post("/api/v1/compare/order", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "validated"
        assert "validation" in data
        assert "metrics" in data
    
    def test_order_validation_with_mismatch(self, client):
        """Test order validation with mismatches."""
        payload = {
            "expected_items": [
                {"name": "apple", "quantity": 2},
                {"name": "banana", "quantity": 1},
            ],
            "detected_items": [
                {"name": "orange", "quantity": 1},
            ],
            "options": {
                "use_semantic": False,
            },
        }
        
        response = client.post("/api/v1/compare/order", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "mismatch"
        assert len(data["validation"]["missing"]) > 0
        assert len(data["validation"]["extra"]) > 0


class TestInventoryValidationEndpoint:
    """Tests for inventory validation endpoint."""
    
    def test_inventory_validation_success(self, client):
        """Test successful inventory validation."""
        payload = {
            "items": ["apple", "banana"],
            "inventory": [
                "Apple - Granny Smith",
                "Banana - Organic",
                "Milk - Whole 1L",
            ],
            "options": {
                "use_semantic": False,
            },
        }
        
        response = client.post("/api/v1/compare/inventory", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "summary" in data
        assert len(data["results"]) == 2


class TestSemanticMatchEndpoint:
    """Tests for semantic match endpoint."""
    
    def test_semantic_match_success(self, client):
        """Test successful semantic matching."""
        with patch("app.services.matchers.semantic.SemanticMatcher.match") as mock_match:
            from app.services.matchers.base import MatchResult
            
            mock_match.return_value = MatchResult(
                match=True,
                confidence=0.95,
                reasoning="Semantic match via VLM",
                match_type="semantic",
            )
            
            payload = {
                "text1": "apple",
                "text2": "green apple",
                "context": "grocery products",
            }
            
            response = client.post("/api/v1/compare/semantic", json=payload)
            
            assert response.status_code == 200
            data = response.json()
            assert data["match"] is True
            assert data["confidence"] > 0.9
            assert "match_type" in data
