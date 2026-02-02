"""
Application state management for tracking initialization status.

This module provides a thread-safe way to track the application's
initialization state, which is used by the health endpoint and
middleware to control API availability.
"""

import logging
import threading
from typing import Optional

from api.api_schemas import AppStatus

logger = logging.getLogger("app_state_manager")


class AppStateManager:
    """
    Thread-safe manager for application state.

    Tracks the current status and optional message describing
    what the application is currently doing.
    """

    def __init__(self) -> None:
        self._status: AppStatus = AppStatus.STARTING
        self._message: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def status(self) -> AppStatus:
        """Returns the current application status."""
        with self._lock:
            return self._status

    @property
    def message(self) -> Optional[str]:
        """Returns the current status message."""
        with self._lock:
            return self._message

    def set_status(self, status: AppStatus, message: Optional[str] = None) -> None:
        """
        Set the application status and optional message.

        Args:
            status: New application status.
            message: Optional message describing current activity.
        """
        with self._lock:
            self._status = status
            self._message = message
            logger.debug(
                f"Application status changed to: {status.value}"
                + (f" - {message}" if message else "")
            )

    def is_ready(self) -> bool:
        """Returns True if the application is ready to serve requests."""
        with self._lock:
            return self._status == AppStatus.READY

    def is_healthy(self) -> bool:
        """
        Returns True if the application is healthy (not shutdown).

        Used by Docker healthcheck - returns healthy during initialization
        so container is not killed while loading resources.
        """
        with self._lock:
            return self._status != AppStatus.SHUTDOWN


# Singleton instance
_app_state_manager: Optional[AppStateManager] = None


def get_app_state_manager() -> AppStateManager:
    """Returns the singleton AppStateManager instance."""
    global _app_state_manager
    if _app_state_manager is None:
        _app_state_manager = AppStateManager()
    return _app_state_manager
