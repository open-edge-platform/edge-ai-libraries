"""
Benchmark Orchestrator

Main orchestration logic for running automated benchmarks.
"""

import time
import logging
import platform
import subprocess
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

from vippet_client import VIPPETClient
from hw_monitor import HardwareMonitor


logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """Represents a single benchmark test case."""

    pipeline_id: str
    pipeline_name: str
    variant_id: str
    variant_name: str
    streams: int
    status: str = "pending"  # pending, running, success, failed, skipped
    job_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    hw_metrics: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None
    attempt: int = 0


@dataclass
class BenchmarkResult:
    """Complete benchmark run results."""

    benchmark_id: str
    timestamp: str
    duration_seconds: float
    config: Dict[str, Any]
    hardware: Dict[str, List[str]]
    test_cases: List[TestCase] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    system_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "benchmark_id": self.benchmark_id,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "config": self.config,
            "hardware": self.hardware,
            "test_cases": [asdict(tc) for tc in self.test_cases],
            "summary": self.summary,
            "system_info": self.system_info,
        }


class BenchmarkOrchestrator:
    """Orchestrates automated benchmark execution."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize orchestrator with configuration.

        Args:
            config: Configuration dictionary loaded from YAML
        """
        self.config = config
        self.client = VIPPETClient(
            base_url=config["vippet"]["base_url"], timeout=config["vippet"]["timeout"]
        )

        # Extract configuration parameters
        self.poll_interval = config["vippet"]["poll_interval"]
        self.max_job_duration = config["vippet"]["max_job_duration"]
        self.max_retries = config["benchmark"]["execution"]["max_retries"]
        self.retry_delay = config["benchmark"]["execution"]["retry_delay_seconds"]
        self.output_mode = config["benchmark"]["execution"]["output_mode"]
        self.require_models = config["benchmark"]["filters"]["require_models"]

        metrics_url = config.get("metrics", {}).get(
            "metrics_url", "http://localhost:9090/api/v1/metrics/latest"
        )
        sample_interval = config.get("metrics", {}).get("sample_interval_seconds", 2.0)
        self.hw_monitor = HardwareMonitor(metrics_url, sample_interval)

        logger.info("Benchmark orchestrator initialized")

    def discover_hardware(self) -> Dict[str, List[str]]:
        """
        Discover available hardware devices.

        Returns:
            Dictionary mapping device family to list of device names
        """
        logger.info("=" * 70)
        logger.info("DISCOVERING HARDWARE")
        logger.info("=" * 70)

        devices = self.client.get_devices()

        hardware = {}
        for device in devices:
            family = device.get("device_family", "").upper()
            name = device.get("device_name", "Unknown")

            if family not in hardware:
                hardware[family] = []
            hardware[family].append(name)

        logger.info("\nAvailable devices:")
        for family, names in sorted(hardware.items()):
            logger.info(f"  ✓ {family}: {', '.join(names)}")

        return hardware

    def check_model_installation(self) -> Dict[str, List[str]]:
        """
        Check which pipelines have models configured in their pipeline graph.
        A pipeline is considered missing models when any gvadetect/gvaclassify/
        gvainference node has an empty 'model' field.

        Returns:
            Dictionary mapping pipeline_id to list of node types missing a model
        """
        if not self.require_models:
            return {}

        logger.info("\nChecking model configuration...")

        pipelines = self.client.get_pipelines()
        missing_models_by_pipeline = {}
        INFERENCE_NODES = {"gvadetect", "gvaclassify", "gvainference"}

        for pipeline in pipelines:
            pipeline_id = pipeline.get("id", "")
            for variant in pipeline.get("variants", []):
                nodes = variant.get("pipeline_graph", {}).get("nodes", [])
                missing = [
                    n["type"]
                    for n in nodes
                    if n.get("type") in INFERENCE_NODES
                    and not n.get("data", {}).get("model", "").strip()
                ]
                if missing:
                    missing_models_by_pipeline[pipeline_id] = missing
                    break  # one variant is enough to flag the pipeline

        if missing_models_by_pipeline:
            logger.warning("\nPipelines skipped (models not configured in VIPPET UI):")
            for pipeline_id, nodes in missing_models_by_pipeline.items():
                logger.warning(
                    f"  - {pipeline_id}: {', '.join(set(nodes))} node(s) have no model set"
                )
        else:
            logger.info("  ✓ All pipeline models are configured")

        return missing_models_by_pipeline

    def generate_test_matrix(
        self, hardware: Dict[str, List[str]], missing_models: Dict[str, List[str]]
    ) -> List[TestCase]:
        """
        Generate test matrix based on available hardware and configuration.

        Args:
            hardware: Available hardware from discover_hardware()
            missing_models: Missing models from check_model_installation()

        Returns:
            List of TestCase objects
        """
        logger.info("\n" + "=" * 70)
        logger.info("GENERATING TEST MATRIX")
        logger.info("=" * 70)

        pipelines = self.client.get_pipelines()
        available_families = set(hardware.keys())

        # Get pipeline filter
        pipeline_filter = self.config["benchmark"]["pipelines"]
        if pipeline_filter != "*":
            pipeline_filter = set(pipeline_filter)

        # Get variant and stream configuration
        requested_variants = set(
            v.upper() for v in self.config["benchmark"]["variants"]
        )
        stream_counts = self.config["benchmark"]["stream_counts"]
        skip_pipelines = set(
            self.config["benchmark"]["filters"].get("skip_pipelines", [])
        )
        skip_variants = set(
            v.upper()
            for v in self.config["benchmark"]["filters"].get("skip_variants", [])
        )

        test_cases = []

        for pipeline in pipelines:
            pipeline_id = pipeline.get("id", "")
            pipeline_name = pipeline.get("name", "")

            if not pipeline_id or not pipeline_name:
                continue

            # Apply pipeline filter
            if pipeline_filter != "*" and pipeline_id not in pipeline_filter:
                continue

            # Skip if explicitly excluded
            if pipeline_id in skip_pipelines:
                logger.info(f"Skipping pipeline (filtered): {pipeline_name}")
                continue

            # Skip if models not installed
            if pipeline_id in missing_models:
                logger.warning(f"Skipping pipeline (missing models): {pipeline_name}")
                continue

            for variant in pipeline.get("variants", []):
                variant_id = variant.get("id", "")
                variant_name = variant.get("name", "").upper()

                if not variant_id or not variant_name:
                    continue

                # Check if variant matches requested device types
                # Variant names can be composite like "GPU_NPU"
                variant_families = set(variant_name.split("_"))

                # Check if all required families are available
                if not variant_families <= available_families:
                    logger.debug(
                        f"Skipping {pipeline_name}/{variant_name} (hardware not available)"
                    )
                    continue

                # Check if variant is in requested list
                if variant_name not in requested_variants and not any(
                    v in requested_variants for v in variant_families
                ):
                    continue

                # Skip if explicitly excluded
                if variant_name in skip_variants:
                    continue

                # Create test cases for each stream count
                for streams in stream_counts:
                    test_case = TestCase(
                        pipeline_id=pipeline_id,
                        pipeline_name=pipeline_name,
                        variant_id=variant_id,
                        variant_name=variant_name,
                        streams=streams,
                    )
                    test_cases.append(test_case)

        logger.info("\nGenerated test matrix:")
        logger.info(f"  Total test cases: {len(test_cases)}")

        # Group by pipeline and variant
        by_pipeline = {}
        for tc in test_cases:
            key = f"{tc.pipeline_name} ({tc.variant_name})"
            by_pipeline[key] = by_pipeline.get(key, 0) + 1

        for pipeline_variant, count in sorted(by_pipeline.items()):
            logger.info(f"  - {pipeline_variant}: {count} stream config(s)")

        return test_cases

    def execute_test_case(self, test_case: TestCase) -> TestCase:
        """
        Execute a single test case with retry logic.

        Args:
            test_case: TestCase to execute

        Returns:
            Updated TestCase with results
        """
        for attempt in range(
            1, self.max_retries + 2
        ):  # +2 because: initial + max_retries
            test_case.attempt = attempt

            try:
                logger.info(f"\n{'─' * 70}")
                logger.info(
                    f"TEST: {test_case.pipeline_name} | "
                    f"{test_case.variant_name} | "
                    f"{test_case.streams} stream(s) | "
                    f"Attempt {attempt}/{self.max_retries + 1}"
                )
                logger.info(f"{'─' * 70}")

                test_case.status = "running"
                start_time = time.time()

                # Submit job
                job_id = self.client.submit_performance_test(
                    pipeline_id=test_case.pipeline_id,
                    variant_id=test_case.variant_id,
                    streams=test_case.streams,
                    output_mode=self.output_mode,
                )
                test_case.job_id = job_id

                # Start HW sampling alongside the running job
                self.hw_monitor.start()

                try:
                    result = self.client.poll_job_completion(
                        job_id=job_id,
                        timeout=self.max_job_duration,
                        poll_interval=self.poll_interval,
                    )
                finally:
                    hw_stats = self.hw_monitor.stop()

                test_case.duration_seconds = time.time() - start_time
                test_case.result = result
                test_case.hw_metrics = hw_stats
                test_case.status = "success"

                # Log key metrics
                total_fps = result.get("total_fps", 0)
                per_stream_fps = result.get("per_stream_fps", 0)
                logger.info("\n✓ SUCCESS")
                logger.info(f"  Total FPS: {total_fps:.2f}")
                logger.info(f"  Per-stream FPS: {per_stream_fps:.2f}")
                logger.info(f"  Duration: {test_case.duration_seconds:.1f}s")
                if hw_stats.get("sample_count", 0) > 0:
                    logger.info(
                        f"  CPU util: {hw_stats.get('cpu_util_pct_avg', 'N/A')}%"
                    )
                    logger.info(
                        f"  NPU util: {hw_stats.get('npu_utilization_avg', 'N/A')}%"
                    )
                    logger.info(
                        f"  GPU render util: {hw_stats.get('gpu_render_util_pct_avg', 'N/A')}%"
                    )
                    logger.info(
                        f"  GPU freq: {hw_stats.get('gpu_freq_mhz_avg', 'N/A')} MHz"
                    )
                    logger.info(
                        f"  GPU power: {hw_stats.get('gpu_power_w_avg', 'N/A')} W"
                    )
                    logger.info(
                        f"  Pkg power: {hw_stats.get('pkg_power_w_avg', 'N/A')} W"
                    )

                return test_case

            except (TimeoutError, RuntimeError) as e:
                test_case.error = str(e)
                logger.error(f"\n✗ FAILED: {e}")

                if attempt <= self.max_retries:
                    logger.info(
                        f"  Retrying in {self.retry_delay}s... ({attempt}/{self.max_retries})"
                    )
                    time.sleep(self.retry_delay)
                else:
                    test_case.status = "failed"
                    logger.error("  Max retries exhausted. Marking as failed.")
                    return test_case

            except Exception as e:
                # Unexpected error - don't retry
                test_case.status = "failed"
                test_case.error = f"Unexpected error: {e}"
                logger.error(f"\n✗ UNEXPECTED ERROR: {e}")
                return test_case

        return test_case

    def run_benchmark(self) -> BenchmarkResult:
        """
        Run complete benchmark suite.

        Returns:
            BenchmarkResult with all test results
        """
        benchmark_id = f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        timestamp = datetime.now().isoformat()
        start_time = time.time()

        logger.info("\n" + "=" * 70)
        logger.info(f"VIPPET BENCHMARK SUITE - {benchmark_id}")
        logger.info("=" * 70)

        # Pre-flight checks
        logger.info("\nPre-flight checks...")
        if not self.client.wait_for_ready(max_wait=60):
            raise RuntimeError("VIPPET API is not ready")

        # Discover hardware
        hardware = self.discover_hardware()

        # Collect system info
        system_info = self._collect_system_info()

        # Check models
        missing_models = self.check_model_installation()

        # Generate test matrix
        test_cases = self.generate_test_matrix(hardware, missing_models)

        if not test_cases:
            logger.warning("\n⚠️  No test cases to run!")
            logger.warning("This could be because:")
            logger.warning("  - No pipelines match the filter")
            logger.warning("  - Required hardware is not available")
            logger.warning("  - All pipelines are missing required models")

        # Execute tests
        logger.info("\n" + "=" * 70)
        logger.info("EXECUTING TESTS")
        logger.info("=" * 70)
        logger.info(f"\nTotal tests: {len(test_cases)}")

        for i, test_case in enumerate(test_cases, 1):
            logger.info(f"\n[{i}/{len(test_cases)}]")
            test_cases[i - 1] = self.execute_test_case(test_case)

        # Calculate summary
        duration = time.time() - start_time
        summary = {
            "total": len(test_cases),
            "success": sum(1 for tc in test_cases if tc.status == "success"),
            "failed": sum(1 for tc in test_cases if tc.status == "failed"),
            "skipped": sum(1 for tc in test_cases if tc.status == "skipped"),
        }

        # Create result
        result = BenchmarkResult(
            benchmark_id=benchmark_id,
            timestamp=timestamp,
            duration_seconds=duration,
            config=self.config,
            hardware=hardware,
            test_cases=test_cases,
            summary=summary,
            system_info=system_info,
        )

        # Print final summary
        logger.info("\n" + "=" * 70)
        logger.info("BENCHMARK COMPLETE")
        logger.info("=" * 70)
        logger.info(f"\nBenchmark ID: {benchmark_id}")
        logger.info(f"Duration: {duration:.1f}s ({duration / 60:.1f}m)")
        logger.info("\nResults:")
        logger.info(f"  ✓ Success: {summary['success']}")
        logger.info(f"  ✗ Failed:  {summary['failed']}")
        logger.info(f"  ⊘ Skipped: {summary['skipped']}")
        logger.info(f"  = Total:   {summary['total']}")

        return result

    def close(self):
        """Clean up resources."""
        self.client.close()

    def _collect_system_info(self) -> Dict[str, Any]:
        """Collect system details for the report."""

        def _cmd(args):
            try:
                return subprocess.check_output(
                    args, text=True, stderr=subprocess.DEVNULL
                ).strip()
            except Exception:
                return ""

        # Processor
        cpu_model = ""
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

        # OS
        os_name = ""
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        os_name = line.split("=", 1)[1].strip().strip('"')
                        break
        except Exception:
            pass

        # Memory
        mem_total = _cmd(["free", "-h", "--si"]).split("\n")
        mem_capacity = ""
        for line in mem_total:
            if line.startswith("Mem:"):
                mem_capacity = line.split()[1]
                break

        # VIPPET version
        vippet_version = ""
        try:
            import requests

            resp = requests.get(f"{self.client.base_url}/version", timeout=5)
            if resp.ok:
                data = resp.json()
                vippet_version = data.get("version", str(data))
        except Exception:
            pass
        if not vippet_version:
            # Fallback: get version from Docker image tag
            tag = _cmd(["docker", "inspect", "--format", "{{.Config.Image}}", "vippet"])
            if ":" in tag:
                vippet_version = tag.split(":", 1)[1]

        return {
            "system": {
                "Processor": cpu_model,
                "Memory": mem_capacity,
                "OS": os_name,
                "Kernel": platform.release(),
            },
            "software": {
                "VIPPET": vippet_version,
            },
        }
