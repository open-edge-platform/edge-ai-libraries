# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Comprehensive test suite for /api/v1/analyze/batch endpoint.

Tests:
1. Successful suspicious activity detection
2. Valid pose detection
3. VLM confirmation enabled/disabled
4. Error cases (no frames, invalid frames, etc.)
5. Request tracking with request_id
6. Different patterns and configurations
"""

import pytest
import requests
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Configuration
API_BASE_URL = "http://localhost:8085"
API_ENDPOINT = f"{API_BASE_URL}/api/v1/analyze/batch"
HEALTH_ENDPOINT = f"{API_BASE_URL}/health"

# Test configuration
TEST_FRAMES_DIR = Path(__file__).parent / "test_frames"
REQUEST_TIMEOUT = 60  # seconds


class TestDataGenerator:
    """Generate test data for API testing."""

    @staticmethod
    def get_test_frames() -> List[Path]:
        """Get generated test frames."""
        if not TEST_FRAMES_DIR.exists():
            pytest.skip(f"Test frames not found at {TEST_FRAMES_DIR}. Run: python generate_test_video.py")

        frames = sorted(TEST_FRAMES_DIR.glob("frame_*.jpg"))
        if not frames:
            pytest.skip(f"No frames found in {TEST_FRAMES_DIR}")

        return frames

    @staticmethod
    def get_frame_subset(start_idx: int = 0, end_idx: int = None, frame_count: int = None) -> List[Path]:
        """
        Get a subset of test frames.
        
        Args:
            start_idx: Starting frame index (default: 0)
            end_idx: Ending frame index (inclusive, default: None = all)
            frame_count: If specified, returns exactly this many frames evenly distributed
        
        Returns:
            List of frame paths
        """
        all_frames = TestDataGenerator.get_test_frames()
        
        if frame_count is not None:
            # Return evenly distributed frames
            if frame_count >= len(all_frames):
                return all_frames
            indices = np.linspace(0, len(all_frames) - 1, frame_count, dtype=int)
            return [all_frames[i] for i in indices]
        else:
            # Return frame range
            if end_idx is None:
                end_idx = len(all_frames)
            return all_frames[start_idx:end_idx]

    @staticmethod
    def prepare_multipart_request(
        frames: List[Path],
        entity_id: str = "test_person_001",
        pattern_id: str = "shelf_to_waist",
        vlm_enabled: bool = None,
        request_id: str = None,
    ) -> Dict[str, Any]:
        """Prepare multipart form-data request."""
        form_data = {
            "entity_id": entity_id,
            "pattern_id": pattern_id,
        }

        if vlm_enabled is not None:
            form_data["vlm_enabled"] = str(vlm_enabled).lower()

        if request_id:
            form_data["request_id"] = request_id

        # Prepare files
        files = []
        for frame_path in frames:
            with open(frame_path, "rb") as f:
                files.append(("frames", (frame_path.name, f, "image/jpeg")))

        return {"data": form_data, "files": files}


class TestAPI:
    """Test suite for /api/v1/analyze/batch endpoint."""

    @pytest.fixture(scope="session", autouse=True)
    def check_service_health(self):
        """Check if service is running before running tests."""
        try:
            response = requests.get(HEALTH_ENDPOINT, timeout=5)
            assert response.status_code == 200, f"Service returned {response.status_code}"
            health = response.json()
            logger.info(f"Service health: {health}")
            assert health["status"] == "healthy", "Service is not healthy"
            assert health["model_loaded"], "Model not loaded"
        except requests.ConnectionError:
            pytest.skip(
                f"Service not running at {API_BASE_URL}. "
                f"Start with: python -m uvicorn src.main:app --host 0.0.0.0 --port 8080"
            )

    def test_01_vlm_confirmation_enabled(self):
        """Test API with VLM confirmation enabled - VLM must be invoked."""
        logger.info("Test: VLM confirmation enabled (strict - VLM must run)")

        # Use all frames for complete pattern detection to trigger VLM
        test_frames = TestDataGenerator.get_frame_subset(start_idx=0, end_idx=24)
        logger.info(f"Using {len(test_frames)} frames (frame_000 to frame_023) for suspicious detection test")


        files = []
        for frame_path in test_frames:
            files.append(("frames", (frame_path.name, open(frame_path, "rb"), "image/jpeg")))

        form_data = {
            "entity_id": "test_person_vlm_enabled",
            "pattern_id": "shelf_to_waist",
            "vlm_enabled": "true",
            "request_id": "req_test_vlm_enabled",
        }

        response = requests.post(API_ENDPOINT, data=form_data, files=files, timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # STRICT ASSERTIONS: When vlm_enabled=true, VLM MUST be invoked
        assert result["status"] == "suspicious", \
            f"Test data must trigger suspicious pattern to test VLM. Got status={result['status']}. " \
            f"This requires synthetic video poses to match pattern geometry."
        
        assert "vlm_confirmed" in result, "vlm_confirmed field must be present"
        assert result["vlm_confirmed"] is not None, \
            "VLM must provide confirmation (True/False) when vlm_enabled=true and pattern matches"
        assert isinstance(result["vlm_confirmed"], bool), \
            f"vlm_confirmed must be boolean, got {type(result['vlm_confirmed'])}"
        
        logger.info(f"✅ VLM invoked successfully. Confirmed: {result['vlm_confirmed']}")

    def test_02_vlm_confirmation_disabled(self):
        """Test API with VLM confirmation disabled - VLM should not be called."""
        logger.info("Test: VLM confirmation disabled")

        # Use frames 5-15 (middle section) for this test
        test_frames = TestDataGenerator.get_frame_subset(start_idx=0, end_idx=24)
        logger.info(f"Using {len(test_frames)} frames (frame_000 to frame_023) for suspicious detection test")

        files = []
        for frame_path in test_frames:
            files.append(("frames", (frame_path.name, open(frame_path, "rb"), "image/jpeg")))

        form_data = {
            "entity_id": "test_person_vlm_disabled",
            "pattern_id": "shelf_to_waist",
            "vlm_enabled": "false",
        }

        response = requests.post(API_ENDPOINT, data=form_data, files=files, timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # When VLM is disabled, vlm_confirmed should be None
        assert result["vlm_confirmed"] is None, \
            f"vlm_confirmed should be None when vlm_enabled=false, got {result['vlm_confirmed']}"
        
        # Response should still have valid structure
        assert result["status"] in ["pose_not_detected", "no_match", "suspicious"]
        logger.info(f"✅ VLM disabled confirmed - vlm_confirmed is None. Status: {result['status']}")

    def test_03_no_match_non_suspicious_frames(self):
        """Test API with non-suspicious frames (no concealment) - should NOT match pattern."""
        logger.info("Test: No match detection on non-suspicious frames (frames 25-30, after concealment window)")

        # Use frames 25-30 (after concealment window ends at ~18s, 32s total video)
        # This should NOT trigger suspicious pattern
        test_frames = TestDataGenerator.get_frame_subset(start_idx=25, end_idx=30)
        logger.info(f"Using {len(test_frames)} frames (frame_025 to frame_029) - outside concealment window")

        files = []
        for frame_path in test_frames:
            files.append(("frames", (frame_path.name, open(frame_path, "rb"), "image/jpeg")))

        form_data = {
            "entity_id": "test_person_no_match",
            "pattern_id": "shelf_to_waist",
            "vlm_enabled": "false",
        }

        response = requests.post(API_ENDPOINT, data=form_data, files=files, timeout=REQUEST_TIMEOUT)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()

        # HARD ASSERTIONS: Non-suspicious frames should NOT trigger pattern match
        assert result["status"] == "no_match", \
            f"HARD: Non-suspicious frames (25-30) must result in no_match status, got {result['status']}"
        
        assert result["pose_detected"] in [True, False], \
            f"HARD: pose_detected must be boolean, got {result['pose_detected']}"
        
        assert "vlm_confirmed" in result, "vlm_confirmed field must be present"
        assert result["vlm_confirmed"] is None, \
            f"HARD: vlm_confirmed should be None when status is no_match, got {result['vlm_confirmed']}"
        
        assert "message" in result and isinstance(result["message"], str), \
            "HARD: Response must include message field with explanation"
        
        assert result["frames_submitted"] == len(test_frames), \
            f"HARD: frames_submitted ({result['frames_submitted']}) must equal submitted count ({len(test_frames)})"
        
        logger.info(f"✅ No match confirmed - status: {result['status']}, frames: {result['frames_submitted']}")

    def test_04_no_frames_returns_custom_400(self):
        """Test API with no frames in request - should return custom 400 error schema."""
        logger.info("Test: No frames provided to batch endpoint")

        form_data = {
            "entity_id": "test_person_no_frames",
            "pattern_id": "shelf_to_waist",
            "vlm_enabled": "false",
        }

        response = requests.post(API_ENDPOINT, data=form_data, timeout=REQUEST_TIMEOUT)

        assert response.status_code == 400, \
            f"Expected 400 when no frames are provided, got {response.status_code}: {response.text}"

        payload = response.json()
        assert "detail" in payload, f"Expected error payload with detail key, got: {payload}"
        assert payload["detail"]["error_code"] == "NO_FRAMES_PROVIDED", \
            f"Expected NO_FRAMES_PROVIDED, got {payload['detail']}"
        assert payload["detail"]["message"] == "At least 1 frame required", \
            f"Unexpected error message: {payload['detail']}"

        logger.info("✅ No-frames request returns custom 400 error schema")

# Test fixture to ensure frames are generated before running tests
@pytest.fixture(scope="session", autouse=True)
def ensure_test_frames():
    """Ensure test frames exist before running tests."""
    if not TEST_FRAMES_DIR.exists() or not list(TEST_FRAMES_DIR.glob("frame_*.jpg")):
        logger.warning(f"Test frames not found at {TEST_FRAMES_DIR}")
        logger.info("Generating test frames...")
        
        try:
            from generate_test_video import create_test_video
            create_test_video(
                output_video_path=str(TEST_FRAMES_DIR.parent / "test_video_suspicious.mp4"),
                output_frames_dir=str(TEST_FRAMES_DIR),
            )
            logger.info("✅ Test frames generated")
        except Exception as e:
            logger.warning(f"Could not auto-generate frames: {e}")
            logger.info(f"Run manually: cd {TEST_FRAMES_DIR.parent} && python generate_test_video.py")


if __name__ == "__main__":
    # Run tests with: pytest tests/test_api_v1_direct.py -v
    pytest.main([__file__, "-v", "-s"])
