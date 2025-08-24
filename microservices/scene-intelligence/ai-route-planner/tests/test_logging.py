#!/usr/bin/env python3
"""
Test script to verify logging functionality in the route agent
"""

import logging
import os
import sys

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("test_route_app.log"), logging.StreamHandler()],
)

from agents.route_agent import get_optimal_route


def test_route_agent():
    """Test the route agent with logging"""
    print("Testing route agent with logging...")

    def mock_progress_callback(text, progress):
        print(f"Progress: {progress:.0%} - {text.split()[-10:]}")  # Show last 10 words

    # Test route planning
    route_info, thinking_output = get_optimal_route(
        "Berkeley, California",
        "Santa Clara, California",
        progress_callback=mock_progress_callback,
    )

    print("\n" + "=" * 50)
    print("ROUTE INFO:")
    print(f"GPX File: {route_info['gpx_file']}")
    print(f"Has Accident: {route_info['has_accident']}")
    print(f"Has Fire: {route_info['has_fire']}")
    print("\n" + "=" * 50)
    print("THINKING OUTPUT (first 500 chars):")
    print(
        thinking_output[:500] + "..." if len(thinking_output) > 500 else thinking_output
    )


if __name__ == "__main__":
    test_route_agent()
