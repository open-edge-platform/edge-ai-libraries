import os
import time
import threading
import pytest
import requests
from unittest import mock
from src.opentelemetry.opentelemetryexport import OpenTelemetryExporter


@pytest.fixture
def otel_exporter():
    """Fixture to create an OpenTelemetryExporter instance."""
    with mock.patch("src.opentelemetry.opentelemetryexport.get_logger") as mock_logger:
        mock_logger.return_value = mock.Mock()
        exporter = OpenTelemetryExporter()

        # Mock the CPU and memory gauges
        exporter.cpu_usage = mock.Mock()
        exporter.memory_usage = mock.Mock()

        return exporter


@mock.patch("src.opentelemetry.opentelemetryexport.requests.get")
def test_fetch_pipeline_fps_success(mock_get, otel_exporter):
    """Test fetching pipeline FPS data when API request is successful."""
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = [
        {"id": "pipeline1", "state": "RUNNING", "avg_fps": 30},
        {"id": "pipeline2", "state": "STOPPED", "avg_fps": 25},
    ]

    fps_data = otel_exporter.fetch_pipeline_fps()
    
    assert fps_data == {"pipeline1": 30}
    otel_exporter.log.debug.assert_called()


@mock.patch("src.opentelemetry.opentelemetryexport.requests.get")
def test_fetch_pipeline_fps_failure(mock_get, otel_exporter):
    """Test handling of API request failure."""
    mock_get.side_effect = requests.RequestException("API request failed")

    fps_data = otel_exporter.fetch_pipeline_fps()
    
    assert fps_data == {}
    otel_exporter.log.error.assert_called()


@mock.patch("src.opentelemetry.opentelemetryexport.psutil.cpu_percent")
@mock.patch("src.opentelemetry.opentelemetryexport.psutil.Process")
def test_get_container_stats(mock_process, mock_cpu, otel_exporter):
    """Test fetching CPU and memory usage statistics."""
    mock_cpu.return_value = 50.5
    mock_process.return_value.memory_info.return_value.rss = 2048576

    cpu, memory = otel_exporter.get_container_stats()
    
    assert cpu == 50.5
    assert memory == 2048576


@mock.patch("src.opentelemetry.opentelemetryexport.metrics.Observation")
@mock.patch("src.opentelemetry.opentelemetryexport.OpenTelemetryExporter.fetch_pipeline_fps")
def test_fps_callback(mock_fetch_fps, mock_observation, otel_exporter):
    """Test the FPS observable gauge callback."""
    mock_fetch_fps.return_value = {"pipeline1": 30}
    mock_observation.return_value = "mock_observation"

    observations = otel_exporter.fps_callback(None)
    
    assert observations == ["mock_observation"]
    mock_observation.assert_called_with(30, {"pipeline_id": "pipeline1"})


def test_start(otel_exporter):
    """Test starting the exporter thread."""
    with mock.patch.object(threading.Thread, "start") as mock_start:
        otel_exporter.start()
        assert otel_exporter._running is True
        mock_start.assert_called_once()
        otel_exporter.log.info.assert_called()


def test_stop(otel_exporter):
    """Test stopping the exporter thread."""
    otel_exporter._running = True
    otel_exporter._thread = mock.Mock()  # Ensure _thread is mocked properly

    with mock.patch.object(otel_exporter._thread, "join") as mock_join:
        otel_exporter.stop()
        assert otel_exporter._running is False
        mock_join.assert_called_once()
        otel_exporter.log.info.assert_called()


@mock.patch("src.opentelemetry.opentelemetryexport.OpenTelemetryExporter.get_container_stats")
def test_export_metrics(mock_get_stats, otel_exporter):
    """Test the metrics export method without getting stuck."""
    mock_get_stats.return_value = (75.5, 4096)

    def stop_after_one_iteration():
        time.sleep(0.1)
        otel_exporter._running = False  # Stop the loop

    otel_exporter._running = True

    # Run export_metrics in a separate thread
    export_thread = threading.Thread(target=otel_exporter.export_metrics)
    export_thread.start()

    stop_after_one_iteration()
    export_thread.join(timeout=1)

    # Ensure CPU and memory metrics are set properly
    otel_exporter.cpu_usage.set.assert_called_with(75.5)
    otel_exporter.memory_usage.set.assert_called_with(4096)
    otel_exporter.log.debug.assert_called()


@mock.patch.dict(os.environ, {
    "SERVICE_NAME": "test_service",
    "OTEL_COLLECTOR_HOST": "test_host",
    "OTEL_COLLECTOR_PORT": "9999",
    "PIPELINE_API_HOST": "api_host",
    "REST_SERVER_PORT": "9090",
    "OTEL_EXPORT_INTERVAL_MILLIS": "5000"
})
@mock.patch("src.opentelemetry.opentelemetryexport.OTLPMetricExporter")
@mock.patch("src.opentelemetry.opentelemetryexport.PeriodicExportingMetricReader")
def test_init(mock_reader, mock_exporter):
    """Test OpenTelemetryExporter initialization with environment variables."""
    with mock.patch("src.opentelemetry.opentelemetryexport.get_logger") as mock_logger:
        mock_logger.return_value = mock.Mock()

        exporter = OpenTelemetryExporter()
        
        assert exporter.collector_url == "http://test_host:9999/v1/metrics"
        assert exporter.api_url == "http://api_host:9090/pipelines/status"
        assert exporter.otlp_exporter == mock_exporter.return_value

        # Ensure the meter is properly initialized (not checking type)
        assert exporter.meter is not None  
        assert exporter.cpu_usage is not None  
        assert exporter.memory_usage is not None  
        
        mock_reader.assert_called()
