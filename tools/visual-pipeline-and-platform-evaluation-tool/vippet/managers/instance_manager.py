import os
import time
import uuid
import threading
import logging
from typing import Dict, Optional
from dataclasses import dataclass

from api.api_schemas import (
    PipelineRequestRun,
    PipelineInstanceState,
    PipelineInstanceStatus,
    PipelineRequestBenchmark,
    PipelineInstanceSummary,
    PipelineType,
)
from gstpipeline import PipelineLoader
from pipeline_runner import PipelineRunner
from benchmark import Benchmark
from utils import download_file, replace_file_path


@dataclass
class PipelineInstance:
    id: str
    name: str
    version: str
    request: PipelineRequestRun | PipelineRequestBenchmark
    state: PipelineInstanceState
    start_time: int
    end_time: Optional[int] = None
    total_fps: Optional[float] = None
    per_stream_fps: Optional[float] = None
    ai_streams: Optional[int] = None
    non_ai_streams: Optional[int] = None
    error_message: Optional[str] = None


class InstanceManager:
    def __init__(self):
        self.instances: Dict[str, PipelineInstance] = {}
        self.runners: Dict[str, PipelineRunner | Benchmark] = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _generate_instance_id() -> str:
        """Generate a unique instance ID using UUID."""
        return uuid.uuid1().hex

    def _start_instance(
        self,
        name: str,
        version: str,
        pipeline_request: PipelineRequestRun | PipelineRequestBenchmark,
        target_func,
    ) -> str:
        """Helper to start a pipeline run or benchmark and return the instance ID."""
        instance_id = self._generate_instance_id()

        # Create instance record
        instance = PipelineInstance(
            id=instance_id,
            name=name,
            version=version,
            request=pipeline_request,
            state=PipelineInstanceState.RUNNING,
            start_time=int(time.time() * 1000),  # milliseconds
        )

        with self.lock:
            self.instances[instance_id] = instance

        # Start execution in background thread
        thread = threading.Thread(
            target=target_func,
            args=(instance_id, name, version, pipeline_request),
            daemon=True,
        )
        thread.start()

        self.logger.info(
            f"{'Pipeline benchmark' if target_func == self._execute_benchmark else 'Pipeline run'} started for instance {instance_id}"
        )

        return instance_id

    def run_pipeline(
        self, name: str, version: str, pipeline_request: PipelineRequestRun
    ) -> str:
        """Start a pipeline run and return the instance ID."""
        return self._start_instance(
            name, version, pipeline_request, self._execute_pipeline
        )

    def benchmark_pipeline(
        self, name: str, version: str, pipeline_request: PipelineRequestBenchmark
    ) -> str:
        """Start a pipeline benchmark and return the instance ID."""
        return self._start_instance(
            name, version, pipeline_request, self._execute_benchmark
        )

    def _build_instance_status(
        self, instance: PipelineInstance
    ) -> PipelineInstanceStatus:
        """Helper to build PipelineInstanceStatus from a PipelineInstance."""
        current_time = int(time.time() * 1000)
        elapsed_time = (
            instance.end_time - instance.start_time
            if instance.end_time
            else current_time - instance.start_time
        )
        return PipelineInstanceStatus(
            id=instance.id,
            start_time=instance.start_time,
            elapsed_time=elapsed_time,
            state=instance.state,
            total_fps=instance.total_fps,
            per_stream_fps=instance.per_stream_fps,
            ai_streams=instance.ai_streams,
            non_ai_streams=instance.non_ai_streams,
            error_message=instance.error_message,
        )

    def get_all_instance_statuses(self) -> list[PipelineInstanceStatus]:
        """Get status of all pipeline instances."""
        with self.lock:
            statuses = [
                self._build_instance_status(instance)
                for instance in self.instances.values()
            ]
            self.logger.debug(f"Current pipeline instance statuses: {statuses}")
            return statuses

    def get_instance_status(self, instance_id: str) -> Optional[PipelineInstanceStatus]:
        """Get status of a specific pipeline instance."""
        with self.lock:
            if instance_id not in self.instances:
                return None
            instance = self.instances[instance_id]
            pipeline_instance_status = self._build_instance_status(instance)
            self.logger.info(
                f"Pipeline instance status for {instance_id}: {pipeline_instance_status}"
            )
            return pipeline_instance_status

    def get_instance_summary(
        self, instance_id: str
    ) -> Optional[PipelineInstanceSummary]:
        """Get summary of a specific pipeline instance."""
        with self.lock:
            if instance_id not in self.instances:
                return None

            instance = self.instances[instance_id]

            pipeline_instance_summary = PipelineInstanceSummary(
                id=instance.id,
                request=instance.request,
                type=PipelineType.GSTREAMER,
            )

            self.logger.debug(
                f"Pipeline instance summary for {instance_id}: {pipeline_instance_summary}"
            )

            return pipeline_instance_summary

    def stop_instance(self, instance_id: str) -> tuple[bool, str]:
        """Stop a running pipeline instance by calling cancel on its runner. Returns (success, message)."""
        with self.lock:
            if instance_id not in self.instances:
                msg = f"Instance {instance_id} not found"
                self.logger.warning(msg)
                return False, msg

            if instance_id not in self.runners:
                msg = f"No active runner found for instance {instance_id}. It may have already completed or was never started."
                self.logger.warning(msg)
                return False, msg

            instance = self.instances[instance_id]

            if instance.state != PipelineInstanceState.RUNNING:
                msg = f"Instance {instance_id} is not running (state: {instance.state})"
                self.logger.warning(msg)
                return False, msg

            runner = self.runners.get(instance_id)
            if runner is None:
                msg = f"No active runner found for instance {instance_id}"
                self.logger.warning(msg)
                return False, msg

        runner.cancel()
        msg = f"Instance {instance_id} stopped"
        self.logger.info(msg)
        return True, msg

    def _update_instance_error(self, instance_id: str, error_message: str):
        """Update instance with error state."""
        with self.lock:
            if instance_id in self.instances:
                instance = self.instances[instance_id]
                instance.state = PipelineInstanceState.ERROR
                instance.end_time = int(time.time() * 1000)
                instance.error_message = error_message
        self.logger.error(f"Pipeline instance {instance_id} error: {error_message}")

    # TODO: Refactor the temporary pipeline execution method
    def _execute_pipeline(
        self,
        instance_id: str,
        name: str,
        version: str,
        pipeline_request: PipelineRequestRun,
    ):
        """Execute the pipeline in a background thread."""
        try:
            # Download the pipeline recording file
            file_name = os.path.basename(str(pipeline_request.source.uri))
            file_path = download_file(
                pipeline_request.source.uri,
                file_name,
            )

            pipeline_description = (
                pipeline_request.parameters.pipeline_graph
            )  # TODO: Convert pipeline_graph in JSON format to pipeline_description

            # Replace file path in launch string if needed
            pipeline_description = replace_file_path(pipeline_description, file_path)

            # Initialize pipeline object from launch string
            gst_pipeline = PipelineLoader.load(pipeline_description)

            inferencing_channels = pipeline_request.parameters.inferencing_channels
            recording_channels = pipeline_request.parameters.recording_channels

            if recording_channels + inferencing_channels == 0:
                self._update_instance_error(
                    instance_id, "At least one channel must be enabled"
                )
                return

            # Initialize PipelineRunner
            runner = PipelineRunner()

            # Store runner for this instance
            with self.lock:
                self.runners[instance_id] = runner

            # Run the pipeline
            results = runner.run(
                pipeline_description=gst_pipeline,
                regular_channels=recording_channels,
                inference_channels=inferencing_channels,
            )

            # Update instance with results
            with self.lock:
                if instance_id in self.instances:
                    instance = self.instances[instance_id]

                    # Check if instance was cancelled while running
                    if runner.is_cancelled():
                        self.logger.info(
                            f"Pipeline {instance_id} was cancelled, updating state to ABORTED"
                        )
                        instance.state = PipelineInstanceState.ABORTED
                        instance.end_time = int(time.time() * 1000)
                        instance.error_message = "Cancelled by user"
                    else:
                        # Normal completion
                        instance.state = PipelineInstanceState.COMPLETED
                        instance.end_time = int(time.time() * 1000)

                        if results is not None:
                            instance.total_fps = results.total_fps
                            instance.per_stream_fps = results.per_stream_fps
                            instance.ai_streams = inferencing_channels
                            instance.non_ai_streams = recording_channels

                # Clean up runner after completion
                self.runners.pop(instance_id, None)

        except Exception as e:
            # Clean up runner on error
            with self.lock:
                self.runners.pop(instance_id, None)
            self._update_instance_error(instance_id, str(e))

    # TODO: Refactor the temporary pipeline benchmark execution method
    def _execute_benchmark(
        self,
        instance_id: str,
        name: str,
        version: str,
        pipeline_request: PipelineRequestBenchmark,
    ):
        """Execute the benchmark in a background thread."""
        try:
            # Download the pipeline recording file
            file_name = os.path.basename(str(pipeline_request.source.uri))
            file_path = download_file(
                pipeline_request.source.uri,
                file_name,
            )

            pipeline_description = (
                pipeline_request.parameters.pipeline_graph
            )  # TODO: Convert pipeline_graph in JSON format to pipeline_description

            # Replace file path in launch string if needed
            pipeline_description = replace_file_path(pipeline_description, file_path)

            # Initialize pipeline object from launch string
            gst_pipeline = PipelineLoader.load(pipeline_description)

            # Initialize Benchmark
            benchmark = Benchmark()

            # Store benchmark runner for this instance
            with self.lock:
                self.runners[instance_id] = benchmark

            # Run the benchmark
            results = benchmark.run(
                pipeline_description=gst_pipeline,
                fps_floor=pipeline_request.parameters.fps_floor,
                rate=pipeline_request.parameters.ai_stream_rate,
            )

            # Update instance with results
            with self.lock:
                if instance_id in self.instances:
                    instance = self.instances[instance_id]

                    # Check if instance was cancelled while running
                    if benchmark.runner.is_cancelled():
                        self.logger.info(
                            f"Benchmark {instance_id} was cancelled, updating state to ABORTED"
                        )
                        instance.state = PipelineInstanceState.ABORTED
                        instance.end_time = int(time.time() * 1000)
                        instance.error_message = "Cancelled by user"
                    else:
                        # Normal completion
                        instance.state = PipelineInstanceState.COMPLETED
                        instance.end_time = int(time.time() * 1000)

                        instance.total_fps = None
                        instance.per_stream_fps = results.per_stream_fps
                        instance.ai_streams = results.ai_streams
                        instance.non_ai_streams = results.non_ai_streams

                        self.logger.info(
                            f"Benchmark completed for instance {instance_id}: streams={results.n_streams}, ai={results.ai_streams}, non_ai={results.non_ai_streams}, fps={results.per_stream_fps}"
                        )

                # Clean up benchmark after completion
                self.runners.pop(instance_id, None)

        except Exception as e:
            # Clean up benchmark on error
            with self.lock:
                self.runners.pop(instance_id, None)
            self._update_instance_error(instance_id, str(e))
