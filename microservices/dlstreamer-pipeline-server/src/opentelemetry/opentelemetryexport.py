#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import time
import os
import psutil
import threading
import requests
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# Additional imports for log exporting
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry import _logs
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

from src.common.log import get_logger

class OpenTelemetryExporter:
    def __init__(self):
        """Initialize the OpenTelemetry metrics exporter."""
        self.log = get_logger(f'{__name__}')

        # Fetch values from environment variables
        service_name = os.getenv("SERVICE_NAME", "dlstreamer-pipeline-server")
        collector_host = os.getenv("OTEL_COLLECTOR_HOST", "otel-collector")
        collector_port = os.getenv("OTEL_COLLECTOR_PORT", "4318")
        self.metrics_collector_url = f"http://{collector_host}:{collector_port}/v1/metrics"
        self.logs_collector_url = f"http://{collector_host}:{collector_port}/v1/logs"

        self.log.debug(f"Collector URL: {self.metrics_collector_url}")

        api_host = os.getenv("PIPELINE_API_HOST", "localhost")
        api_port = os.getenv("REST_SERVER_PORT", "8080")
        self.api_url = f"http://{api_host}:{api_port}/pipelines/status"
        
        # How often to export metrics to the collector
        # 10 seconds by default, but can be overridden by setting the env variable it
        otel_export_interval_millis = int(os.getenv("OTEL_EXPORT_INTERVAL_MILLIS", 10000))  # 10 seconds

        # Initialize OpenTelemetry for metrics with dynamic service name
        resource = Resource(attributes={"service.name": service_name})

        # Create the OTLP Metric Exporter
        self.otlp_metrics_exporter = OTLPMetricExporter(endpoint=self.metrics_collector_url)
        # Create the OTLP Log Exporter
        self.otlp_logs_exporter = OTLPLogExporter(endpoint=self.logs_collector_url)

        # Set up the PeriodicExportingMetricReader, which sends metrics to the OTLP exporter
        metric_reader = PeriodicExportingMetricReader(
            exporter=self.otlp_metrics_exporter, 
            export_interval_millis=otel_export_interval_millis
        )
        
        # Initialize the MeterProvider with the Resource and Metric Reader
        meter_provider = MeterProvider(
            resource=resource, 
            metric_readers=[metric_reader]
        )
        
        # Set the global MeterProvider
        metrics.set_meter_provider(meter_provider)
        
        # Create a Meter object to capture metrics
        self.meter = meter_provider.get_meter("container-metrics")
        
        # Set up LoggerProvider with resource info
        logger_provider = LoggerProvider(resource=resource)
        # set_logger_provider(logger_provider)
        # Set it as the global logger provider
        _logs.set_logger_provider(logger_provider)

        # Add OTLP log exporter processor
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(self.otlp_logs_exporter)
        )

        # Attach OpenTelemetry logging handler to root logger
        import logging
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.NOTSET)
        otel_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log.info(f"Setting OpenTelemetry log level to: {otel_log_level}")
        otel_logging_handler = LoggingHandler(level=getattr(logging, otel_log_level, logging.DEBUG))
        root_logger.addHandler(otel_logging_handler)

        # Create gauges to track CPU and memory usage
        self.cpu_usage = self.meter.create_gauge(
            "cpu_usage_percentage",
            description="Tracks CPU usage percentage of DLStreamer pipeline server python process"
        )

        self.memory_usage = self.meter.create_gauge(
            "memory_usage_bytes",
            description="Tracks memory usage in bytes of DLStreamer pipeline server python process"
        )

        # Use Observable Gauge for FPS as it contains attributes
        self.fps_gauge = self.meter.create_observable_gauge(
            "fps_per_pipeline",
            callbacks=[self.fps_callback],
            description="Tracks FPS for each active pipeline instance in DLStreamer Pipeline Server"
        )

        # Initialize threading
        self._running = False
        self._thread = None

    def get_container_stats(self):
        """Get CPU and memory usage stats of the current process."""
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)

        # Get memory usage
        memory_usage = psutil.Process(os.getpid()).memory_info().rss  # Memory in bytes

        return cpu_percent, memory_usage

    def fetch_pipeline_fps(self):
        """Fetch FPS data from the API and update metrics."""
        try:
            response = requests.get(self.api_url, timeout=5)  # 5-second timeout
            if response.status_code == 200:
                pipelines = response.json()
                self.log.debug(f"Pipeline API Response: {pipelines}")

                fps_data = {}
                for pipeline in pipelines:
                    if pipeline["state"] == "RUNNING":  # Only consider running pipelines
                        pipeline_id = pipeline["id"]
                        avg_fps = pipeline["avg_fps"]

                        fps_data[pipeline_id] = avg_fps
                        self.log.debug(f"Extracted FPS Data: {fps_data}")
                return fps_data
            else:
                self.log.error(f"Failed to fetch pipeline data. Status code: {response.status_code}")
        except requests.RequestException as e:
            self.log.error(f"Error fetching pipeline data: {e}")
        return {}

    def fps_callback(self, options):
        """Observable gauge callback for FPS metrics."""
        fps_data = self.fetch_pipeline_fps()
        if not fps_data:
            self.log.debug("No FPS data available.")
            return []
        self.log.debug("Adding FPS Metrics to OpenTelemetry: {}".format(fps_data))
        return [
            metrics.Observation(fps, {"pipeline_id": pipeline_id})
            for pipeline_id, fps in fps_data.items()
        ]


    def export_metrics(self):
        """Collect container CPU and memory metrics and expose them to OpenTelemetry Collector."""
        while self._running:
            try:
                # Fetch stats for CPU and memory usage
                cpu, memory = self.get_container_stats()

                # Report metrics to OpenTelemetry
                self.cpu_usage.set(cpu)  # Report CPU usage percentage
                self.memory_usage.set(memory)  # Report memory usage in bytes

                self.log.debug(f"Added new metrics - CPU: {cpu}%, Memory: {memory} bytes")
                time.sleep(1)  # Sleep for 1 second before the next collection
            except Exception as e:
                self.log.error(f"Error exporting CPU and memory metrics: {e}")

    def start(self):
        """Start the metrics collection in a new thread."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self.export_metrics, daemon=True)
            self._thread.start()
            self.log.info("OpenTelemetry Metrics collection started.")

    def stop(self):
        """Stop the metrics collection gracefully."""
        if self._running:
            self._running = False
            self._thread.join()  # Wait for the thread to finish
            self.log.info("OpenTelemetry Metrics collection stopped.")
