import unittest

from internal_types import InternalAppStatus
from managers.app_state_manager import AppStateManager


class TestAppStateManager(unittest.TestCase):
    """
    Unit tests for AppStateManager.

    The tests focus on:
      * initial state after creation,
      * status transitions,
      * is_ready and is_healthy behavior,
      * thread-safe property access.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        AppStateManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        AppStateManager._instance = None

    # ------------------------------------------------------------------
    # Singleton tests
    # ------------------------------------------------------------------

    def test_singleton_returns_same_instance(self):
        """AppStateManager() should return the same instance on multiple calls."""
        instance1 = AppStateManager()
        instance2 = AppStateManager()
        self.assertIs(instance1, instance2)

    # ------------------------------------------------------------------
    # Initial state tests
    # ------------------------------------------------------------------

    def test_initial_status_is_starting(self):
        """New AppStateManager should have STARTING status."""
        manager = AppStateManager()
        self.assertEqual(manager.status, InternalAppStatus.STARTING)

    def test_initial_message_is_none(self):
        """New AppStateManager should have no message."""
        manager = AppStateManager()
        self.assertIsNone(manager.message)

    def test_initial_is_ready_returns_false(self):
        """New AppStateManager should not be ready."""
        manager = AppStateManager()
        self.assertFalse(manager.is_ready())

    def test_initial_is_healthy_returns_true(self):
        """New AppStateManager should be healthy (not in shutdown)."""
        manager = AppStateManager()
        self.assertTrue(manager.is_healthy())

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def test_set_status_changes_status(self):
        """set_status should update the status property."""
        manager = AppStateManager()

        manager.set_status(InternalAppStatus.INITIALIZING)
        self.assertEqual(manager.status, InternalAppStatus.INITIALIZING)

        manager.set_status(InternalAppStatus.READY)
        self.assertEqual(manager.status, InternalAppStatus.READY)

        manager.set_status(InternalAppStatus.SHUTDOWN)
        self.assertEqual(manager.status, InternalAppStatus.SHUTDOWN)

    def test_set_status_updates_message(self):
        """set_status should update the message property."""
        manager = AppStateManager()

        manager.set_status(InternalAppStatus.INITIALIZING, "Loading videos...")
        self.assertEqual(manager.message, "Loading videos...")

        manager.set_status(InternalAppStatus.READY, None)
        self.assertIsNone(manager.message)

    def test_set_status_clears_previous_message(self):
        """set_status without message should clear previous message."""
        manager = AppStateManager()

        manager.set_status(InternalAppStatus.INITIALIZING, "Step 1")
        self.assertEqual(manager.message, "Step 1")

        manager.set_status(InternalAppStatus.INITIALIZING)
        self.assertIsNone(manager.message)

    # ------------------------------------------------------------------
    # is_ready behavior
    # ------------------------------------------------------------------

    def test_is_ready_returns_false_for_starting(self):
        """is_ready should return False for STARTING status."""
        manager = AppStateManager()
        manager.set_status(InternalAppStatus.STARTING)
        self.assertFalse(manager.is_ready())

    def test_is_ready_returns_false_for_initializing(self):
        """is_ready should return False for INITIALIZING status."""
        manager = AppStateManager()
        manager.set_status(InternalAppStatus.INITIALIZING)
        self.assertFalse(manager.is_ready())

    def test_is_ready_returns_true_for_ready(self):
        """is_ready should return True only for READY status."""
        manager = AppStateManager()
        manager.set_status(InternalAppStatus.READY)
        self.assertTrue(manager.is_ready())

    def test_is_ready_returns_false_for_shutdown(self):
        """is_ready should return False for SHUTDOWN status."""
        manager = AppStateManager()
        manager.set_status(InternalAppStatus.SHUTDOWN)
        self.assertFalse(manager.is_ready())

    # ------------------------------------------------------------------
    # is_healthy behavior
    # ------------------------------------------------------------------

    def test_is_healthy_returns_true_for_starting(self):
        """is_healthy should return True for STARTING status."""
        manager = AppStateManager()
        manager.set_status(InternalAppStatus.STARTING)
        self.assertTrue(manager.is_healthy())

    def test_is_healthy_returns_true_for_initializing(self):
        """is_healthy should return True for INITIALIZING status."""
        manager = AppStateManager()
        manager.set_status(InternalAppStatus.INITIALIZING)
        self.assertTrue(manager.is_healthy())

    def test_is_healthy_returns_true_for_ready(self):
        """is_healthy should return True for READY status."""
        manager = AppStateManager()
        manager.set_status(InternalAppStatus.READY)
        self.assertTrue(manager.is_healthy())

    def test_is_healthy_returns_false_for_shutdown(self):
        """is_healthy should return False only for SHUTDOWN status."""
        manager = AppStateManager()
        manager.set_status(InternalAppStatus.SHUTDOWN)
        self.assertFalse(manager.is_healthy())

    # ------------------------------------------------------------------
    # InternalAppStatus enum
    # ------------------------------------------------------------------

    def test_internal_app_status_values(self):
        """InternalAppStatus enum should have expected string values."""
        self.assertEqual(InternalAppStatus.STARTING.value, "starting")
        self.assertEqual(InternalAppStatus.INITIALIZING.value, "initializing")
        self.assertEqual(InternalAppStatus.READY.value, "ready")
        self.assertEqual(InternalAppStatus.SHUTDOWN.value, "shutdown")

    def test_internal_app_status_is_str_enum(self):
        """InternalAppStatus should be usable as string."""
        self.assertIsInstance(InternalAppStatus.READY, str)
        # When used as str directly (not via str() function), it equals its value
        self.assertEqual(InternalAppStatus.READY.value, "ready")
        # The enum inherits from str, so it can be compared directly
        self.assertEqual(InternalAppStatus.READY, "ready")


class TestAppStateManagerErrorStatus(unittest.TestCase):
    """Tests for ERROR status handling in AppStateManager."""

    def test_error_status_not_defined(self):
        """InternalAppStatus should not have ERROR value - only STARTING, INITIALIZING, READY, SHUTDOWN."""
        # Verify ERROR is not in the enum
        status_values = [s.value for s in InternalAppStatus]
        self.assertNotIn("error", status_values)
        self.assertIn("starting", status_values)
        self.assertIn("initializing", status_values)
        self.assertIn("ready", status_values)
        self.assertIn("shutdown", status_values)


if __name__ == "__main__":
    unittest.main()
