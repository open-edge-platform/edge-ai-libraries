import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from unittest.mock import patch, MagicMock

from api.api_schemas import AppStatus
from api.routes.health import router as health_router


class TestHealthAPI(unittest.TestCase):
    """
    Unit tests for the health and status HTTP API endpoints.

    The tests use FastAPI's TestClient and patch the
    ``AppStateManager`` class to control the behavior
    of the underlying state manager without touching its real implementation.
    """

    @classmethod
    def setUpClass(cls):
        """Set up test client once for all tests."""
        app = FastAPI()
        app.include_router(health_router, tags=["health"])
        cls.client = TestClient(app)

    # ------------------------------------------------------------------
    # /health endpoint tests
    # ------------------------------------------------------------------

    @patch("api.routes.health.AppStateManager")
    def test_get_health_returns_healthy_true_when_not_shutdown(
        self, mock_app_state_manager_cls
    ):
        """Test GET /health returns healthy=true when app is not in shutdown state."""
        mock_manager = MagicMock()
        mock_manager.is_healthy.return_value = True
        mock_app_state_manager_cls.return_value = mock_manager

        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("healthy", data)
        self.assertTrue(data["healthy"])
        mock_manager.is_healthy.assert_called_once()

    @patch("api.routes.health.AppStateManager")
    def test_get_health_returns_healthy_false_when_shutdown(
        self, mock_app_state_manager_cls
    ):
        """Test GET /health returns healthy=false when app is in shutdown state."""
        mock_manager = MagicMock()
        mock_manager.is_healthy.return_value = False
        mock_app_state_manager_cls.return_value = mock_manager

        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("healthy", data)
        self.assertFalse(data["healthy"])
        mock_manager.is_healthy.assert_called_once()

    # ------------------------------------------------------------------
    # /status endpoint tests
    # ------------------------------------------------------------------

    @patch("api.routes.health.AppStateManager")
    def test_get_status_returns_initializing_state(self, mock_app_state_manager_cls):
        """Test GET /status returns correct data during initialization."""
        mock_manager = MagicMock()
        mock_manager.status = AppStatus.INITIALIZING
        mock_manager.message = "Loading video metadata..."
        mock_manager.is_ready.return_value = False
        mock_app_state_manager_cls.return_value = mock_manager

        response = self.client.get("/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], AppStatus.INITIALIZING.value)
        self.assertEqual(data["message"], "Loading video metadata...")
        self.assertFalse(data["ready"])
        mock_manager.is_ready.assert_called_once()

    @patch("api.routes.health.AppStateManager")
    def test_get_status_returns_ready_state(self, mock_app_state_manager_cls):
        """Test GET /status returns correct data when app is ready."""
        mock_manager = MagicMock()
        mock_manager.status = AppStatus.READY
        mock_manager.message = None
        mock_manager.is_ready.return_value = True
        mock_app_state_manager_cls.return_value = mock_manager

        response = self.client.get("/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], AppStatus.READY.value)
        self.assertIsNone(data["message"])
        self.assertTrue(data["ready"])
        mock_manager.is_ready.assert_called_once()

    @patch("api.routes.health.AppStateManager")
    def test_get_status_returns_starting_state(self, mock_app_state_manager_cls):
        """Test GET /status returns correct data when app is starting."""
        mock_manager = MagicMock()
        mock_manager.status = AppStatus.STARTING
        mock_manager.message = None
        mock_manager.is_ready.return_value = False
        mock_app_state_manager_cls.return_value = mock_manager

        response = self.client.get("/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], AppStatus.STARTING.value)
        self.assertIsNone(data["message"])
        self.assertFalse(data["ready"])

    @patch("api.routes.health.AppStateManager")
    def test_get_status_returns_shutdown_state(self, mock_app_state_manager_cls):
        """Test GET /status returns correct data when app is shutting down."""
        mock_manager = MagicMock()
        mock_manager.status = AppStatus.SHUTDOWN
        mock_manager.message = "Shutting down..."
        mock_manager.is_ready.return_value = False
        mock_app_state_manager_cls.return_value = mock_manager

        response = self.client.get("/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], AppStatus.SHUTDOWN.value)
        self.assertEqual(data["message"], "Shutting down...")
        self.assertFalse(data["ready"])

    # ------------------------------------------------------------------
    # Router metadata tests
    # ------------------------------------------------------------------

    def test_operation_ids_are_exposed_as_expected(self):
        """
        Ensure that the router in health.py is configured with the expected
        operation_id values.

        This test does not perform any HTTP calls; instead it inspects
        the FastAPI route definitions.
        """
        operations = {}
        for route in health_router.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods:
                operations[(route.path, method)] = route.operation_id

        self.assertIn(("/health", "GET"), operations)
        self.assertIn(("/status", "GET"), operations)

        self.assertEqual(operations[("/health", "GET")], "get_health")
        self.assertEqual(operations[("/status", "GET")], "get_status")


if __name__ == "__main__":
    unittest.main()
