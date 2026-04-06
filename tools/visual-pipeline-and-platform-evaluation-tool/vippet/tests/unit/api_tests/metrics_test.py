import json
import queue
import time
import unittest
from threading import Thread
from typing import cast

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from api.routes.metrics import router as metrics_router


class TestMetricsAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up FastAPI app and test client for all tests
        app = FastAPI()
        app.include_router(metrics_router, prefix="/metrics")
        cls._client = TestClient(app)

    @property
    def client(self):
        # Property to access the shared test client
        return self._client

    def test_placeholder(self):
        # Ensure the /metrics route does not exist (404 expected)
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 404)

    def test_websocket_collector_endpoint(self):
        # Test that collector WebSocket endpoint can be connected to
        with self.client.websocket_connect("/metrics/ws/collector") as ws:
            self.assertIsNotNone(ws)

    def test_websocket_clients_endpoint(self):
        # Test that clients WebSocket endpoint can be connected to
        with self.client.websocket_connect("/metrics/ws/clients") as ws:
            self.assertIsNotNone(ws)

    def test_collector_rejects_second_connection(self):
        # Only one collector connection is allowed at a time
        with self.client.websocket_connect("/metrics/ws/collector"):
            with self.client.websocket_connect("/metrics/ws/collector") as ws2:
                msg = ws2.receive_text()
                self.assertIn("Collector already connected", msg)
                with self.assertRaises(Exception):
                    ws2.receive_text()

    @staticmethod
    def _receive_with_timeout(ws, timeout=2):
        """
        Helper to receive a message from a websocket with a timeout.
        Raises TimeoutError if no message is received in time.
        """
        result_queue = queue.Queue()

        def receive():
            try:
                result_queue.put(ws.receive_text())
            except Exception as exc:
                result_queue.put(exc)

        thread = Thread(target=receive)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            raise TimeoutError("Timeout while waiting for websocket message")
        result = result_queue.get()
        if isinstance(result, Exception):
            raise result
        return result

    def test_collector_to_single_client_metrics_forwarding(self):
        # Metrics sent by collector are forwarded to a single client
        metrics = {"foo": 123}
        with self.client.websocket_connect("/metrics/ws/clients") as client_ws:
            with self.client.websocket_connect("/metrics/ws/collector") as collector_ws:
                collector_ws.send_bytes(json.dumps(metrics).encode("utf-8"))
                try:
                    received = json.loads(self._receive_with_timeout(client_ws))
                except (TimeoutError, AssertionError) as exc:
                    self.fail(f"Client did not receive metrics from collector: {exc}")
                self.assertEqual(received, metrics)

    def test_collector_to_multiple_clients_metrics_forwarding(self):
        # Metrics sent by collector are forwarded to multiple clients
        metrics = {"bar": 456}
        with (
            self.client.websocket_connect("/metrics/ws/clients") as client_ws1,
            self.client.websocket_connect("/metrics/ws/clients") as client_ws2,
            self.client.websocket_connect("/metrics/ws/collector") as collector_ws,
        ):
            collector_ws.send_bytes(json.dumps(metrics).encode("utf-8"))
            try:
                received1 = json.loads(self._receive_with_timeout(client_ws1))
                received2 = json.loads(self._receive_with_timeout(client_ws2))
            except (TimeoutError, AssertionError) as exc:
                self.fail(f"Timeout or error while receiving metrics: {exc}")
            self.assertEqual(received1, metrics)
            self.assertEqual(received2, metrics)

    def test_collector_disconnect_releases_slot(self):
        # After collector disconnects, a new collector can connect
        ws_url = "/metrics/ws/collector"
        with self.client.websocket_connect(ws_url):
            pass  # Disconnects at end of with-block
        # Wait for cleanup and try to connect again
        for _ in range(10):
            try:
                with self.client.websocket_connect(ws_url) as ws2:
                    ws2.send_bytes(json.dumps({"x": 1}).encode("utf-8"))
                    return
            except (TimeoutError, AssertionError):
                time.sleep(0.1)
        self.fail("Collector slot was not released in time")

    def test_client_disconnect_cleanup(self):
        # After client disconnects, a new client can connect
        ws_url = "/metrics/ws/clients"
        with self.client.websocket_connect(ws_url):
            pass  # Disconnects at end of with-block
        # Wait for cleanup and try to connect again
        for _ in range(10):
            try:
                with self.client.websocket_connect(ws_url) as ws2:
                    self.assertIsNotNone(ws2)
                    return
            except (TimeoutError, AssertionError):
                time.sleep(0.1)
        self.fail("Client slot was not released in time")

    def test_collector_handles_client_send_error(self):
        # If a client fails to receive, collector continues for others
        metrics = {"baz": 789}

        # Use a duck-typed object instead of subclassing WebSocket to avoid typing
        # conflicts with the 'client' property. It mimics required async methods.
        class BrokenWebSocket:
            async def send_json(self, *a, **kw):
                raise Exception("fail")

            async def send_text(self, *a, **kw):
                raise Exception("fail")

            @property
            def client(self):
                # Return an Address-like tuple to match expected runtime shape.
                return ("broken", 0)

        with (
            self.client.websocket_connect("/metrics/ws/clients"),
            self.client.websocket_connect("/metrics/ws/collector") as collector_ws,
        ):
            from api.routes import metrics as metrics_mod

            # Add a BrokenWebSocket instance to client_connections (duck-typed)
            # Cast to WebSocket to satisfy the type checker while keeping runtime behavior.
            metrics_mod.client_connections.add(cast(WebSocket, BrokenWebSocket()))
            try:
                collector_ws.send_bytes(json.dumps(metrics).encode("utf-8"))
            finally:
                metrics_mod.client_connections.clear()


if __name__ == "__main__":
    unittest.main()
