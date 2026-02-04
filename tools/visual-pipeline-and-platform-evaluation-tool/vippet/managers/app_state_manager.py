"""
Application state management for tracking initialization status.

This module provides a thread-safe singleton for tracking the application's
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
    Thread-safe singleton manager for application state.

    Tracks the current status and optional message describing
    what the application is currently doing.

    This class implements the singleton pattern using __new__ with
    double-checked locking. Create instances with AppStateManager()
    to get the shared singleton instance.
    """

    _instance: Optional["AppStateManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "AppStateManager":
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Protect against multiple initialization
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self._status: AppStatus = AppStatus.STARTING
        self._message: Optional[str] = None
        self._state_lock = threading.Lock()

    @property
    def status(self) -> AppStatus:
        """Returns the current application status."""
        with self._state_lock:
            return self._status

    @property
    def message(self) -> Optional[str]:
        """Returns the current status message."""
        with self._state_lock:
            return self._message

    def set_status(self, status: AppStatus, message: Optional[str] = None) -> None:
        """
        Set the application status and optional message.

        Args:
            status: New application status.
            message: Optional message describing current activity.
        """
        with self._state_lock:
            self._status = status
            self._message = message
            logger.debug(
                f"Application status changed to: {status.value}"
                + (f" - {message}" if message else "")
            )

    def is_ready(self) -> bool:
        """Returns True if the application is ready to serve requests."""
        with self._state_lock:
            return self._status == AppStatus.READY

    def is_healthy(self) -> bool:
        """
        Returns True if the application is healthy (not shutdown).

        Used by Docker healthcheck - returns healthy during initialization
        so container is not killed while loading resources.
        """
        with self._state_lock:
            return self._status != AppStatus.SHUTDOWN
