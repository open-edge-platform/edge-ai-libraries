from abc import ABC, abstractmethod
from typing import Optional, List

from schema import RouteCondition


class RouteStatusInterface(ABC):
    """
    Interface for implementing controllers which provide information and details about routes.
    """

    @property
    @abstractmethod
    def latitude(self) -> Optional[float]:
        """
        Abstract property for the latitude coordinate.

        Returns:
            float: The latitude value.
        """
        pass

    @property
    @abstractmethod
    def longitude(self) -> Optional[float]:
        """
        Abstract property for the longitude coordinate.

        Returns:
            float: The longitude value.
        """
        pass

    @property
    @abstractmethod
    def proximity_factor(self) -> float:
        """
        A float integer to help consider nearby latitude and longitudes as well,
        as a matching location coordinates.
        """
        pass

    @abstractmethod
    def fetch_route_status(self) -> Optional[List[RouteCondition] | RouteCondition]:
        """
        Fetch route status based on implementation-specific criteria.

        Returns:
            RouteCondition: The travel conditions for the route.
        """
        pass
