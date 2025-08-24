import requests
from typing import Dict, Any, Optional

from config import (
    SCENE_INTELLIGENCE_API_BASE,
    SCENE_INTELLIGENCE_ENDPOINTS,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)

class ThresholdController:
    """
    Controller for updating traffic threshold values via the Scene Intelligence API.
    """

    TRAFFIC_DENSITY_THRESHOLD: int = 5

    def __init__(self):
        self.api_base = SCENE_INTELLIGENCE_API_BASE
        self.threshold_endpoint = SCENE_INTELLIGENCE_ENDPOINTS["update_threshold"]
    
    def update_threshold(self, threshold_value: int) -> Dict[str, Any]:
        """
        Update the traffic density threshold value in the Scene Intelligence API.
        
        Args:
            threshold_value (int): The new threshold value (1-15)
            
        Returns:
            Dict[str, Any]: The API response containing status information
        """
        try:
            logger.info(f"Updating traffic density threshold to {threshold_value}...")

            ThresholdController.TRAFFIC_DENSITY_THRESHOLD = threshold_value

            api_url = f"{self.api_base}{self.threshold_endpoint}"
            payload = {
                "threshold": threshold_value
            }
            
            response = requests.put(api_url, json=payload)
            response.raise_for_status() 
            
            data = response.json()
            logger.info(f"Successfully updated traffic density threshold to {threshold_value}")
            return data
            
        except Exception as e:
            logger.error(f"Error updating threshold value: {e}")
            return {"error": str(e), "success": False}
