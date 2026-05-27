"""Abstract base class for delivery handlers."""

from __future__ import annotations

import abc

from src.core.config import DeliveryTarget
from src.core.models import AlertEnvelope


class DeliveryHandler(abc.ABC):
    """Base delivery handler interface."""

    @abc.abstractmethod
    async def deliver(
        self, envelope: AlertEnvelope, target: DeliveryTarget
    ) -> None:
        """Deliver an alert to the configured target. Raises on failure."""
