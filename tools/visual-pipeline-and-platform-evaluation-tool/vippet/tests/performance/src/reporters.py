# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Result Reporters

Export benchmark results in various formats.
"""

import json
import csv
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class JSONReporter:
    """Export results as JSON."""

    @staticmethod
    def save(result: dict[str, Any], output_path: Path):
        """
        Save results as JSON file.

        Args:
            result: BenchmarkResult dictionary
            output_path: Output file path
        """
        logger.info(f"Saving JSON report: {output_path}")

        with open(output_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        logger.info(f"  ✓ JSON report saved ({output_path.stat().st_size} bytes)")


class CSVReporter:
    """Export results as CSV."""

    @staticmethod
    def save(result: dict[str, Any], output_path: Path):
        """
        Save results as CSV file.

        Args:
            result: BenchmarkResult dictionary
            output_path: Output file path
        """
        logger.info(f"Saving CSV report: {output_path}")

        test_cases = result.get("test_cases", [])

        if not test_cases:
            logger.warning("  No test cases to export to CSV")
            return

        # Define CSV columns
        fieldnames = [
            "pipeline_name",
            "pipeline_id",
            "variant_name",
            "variant_id",
            "streams",
            "status",
            "total_fps",
            "per_stream_fps",
            "duration_seconds",
            # CPU KPIs
            "cpu_util_pct_avg",
            "cpu_util_pct_max",
            "cpu_freq_mhz_avg",
            "cpu_temperature_avg",
            "mem_used_percent_avg",
            # GPU KPIs (metrics-manager)
            "gpu_render_util_pct_avg",
            "gpu_render_util_pct_max",
            "gpu_video_util_pct_avg",
            "gpu_compute_util_pct_avg",
            "gpu_util_combined_avg",
            "gpu_freq_mhz_avg",
            "gpu_power_w_avg",
            "pkg_power_w_avg",
            # NPU KPIs (metrics-manager)
            "npu_utilization_avg",
            "npu_utilization_max",
            "npu_power_avg",
            "npu_frequency_avg",
            "npu_temperature_avg",
            "npu_memory_mb_avg",
            "npu_bandwidth_avg",
            "hw_sample_count",
            "job_id",
            "error",
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for tc in test_cases:
                result_data = tc.get("result", {}) or {}
                total_fps = result_data.get("total_fps", None)
                per_stream_fps = result_data.get("per_stream_fps", None)
                hw = tc.get("hw_metrics", {}) or {}

                def _f(key: str) -> str:
                    v = hw.get(key)
                    return f"{v:.2f}" if v is not None else ""

                row = {
                    "pipeline_name": tc.get("pipeline_name", ""),
                    "pipeline_id": tc.get("pipeline_id", ""),
                    "variant_name": tc.get("variant_name", ""),
                    "variant_id": tc.get("variant_id", ""),
                    "streams": tc.get("streams", 0),
                    "status": tc.get("status", ""),
                    "total_fps": f"{total_fps:.2f}" if total_fps is not None else "",
                    "per_stream_fps": f"{per_stream_fps:.2f}"
                    if per_stream_fps is not None
                    else "",
                    "duration_seconds": f"{tc.get('duration_seconds', 0):.1f}"
                    if tc.get("duration_seconds")
                    else "",
                    "cpu_util_pct_avg": _f("cpu_util_pct_avg"),
                    "cpu_util_pct_max": _f("cpu_util_pct_max"),
                    "cpu_freq_mhz_avg": _f("cpu_freq_mhz_avg"),
                    "cpu_temperature_avg": _f("cpu_temperature_avg"),
                    "mem_used_percent_avg": _f("mem_used_percent_avg"),
                    "gpu_render_util_pct_avg": _f("gpu_render_util_pct_avg"),
                    "gpu_render_util_pct_max": _f("gpu_render_util_pct_max"),
                    "gpu_video_util_pct_avg": _f("gpu_video_util_pct_avg"),
                    "gpu_compute_util_pct_avg": _f("gpu_compute_util_pct_avg"),
                    "gpu_util_combined_avg": _f("gpu_util_combined_avg"),
                    "gpu_freq_mhz_avg": _f("gpu_freq_mhz_avg"),
                    "gpu_power_w_avg": _f("gpu_power_w_avg"),
                    "pkg_power_w_avg": _f("pkg_power_w_avg"),
                    "npu_utilization_avg": _f("npu_utilization_avg"),
                    "npu_utilization_max": _f("npu_utilization_max"),
                    "npu_power_avg": _f("npu_power_avg"),
                    "npu_frequency_avg": _f("npu_frequency_avg"),
                    "npu_temperature_avg": _f("npu_temperature_avg"),
                    "npu_memory_mb_avg": _f("npu_memory_mb_avg"),
                    "npu_bandwidth_avg": _f("npu_bandwidth_avg"),
                    "hw_sample_count": hw.get("sample_count", ""),
                    "job_id": tc.get("job_id", ""),
                    "error": tc.get("error", ""),
                }
                writer.writerow(row)

        logger.info(f"  ✓ CSV report saved ({len(test_cases)} rows)")


class MarkdownReporter:
    """Export results as Markdown summary."""

    @staticmethod
    def save(result: dict[str, Any], output_path: Path):
        """
        Save results as Markdown file.

        Args:
            result: BenchmarkResult dictionary
            output_path: Output file path
        """
        logger.info(f"Saving Markdown report: {output_path}")

        lines = []

        # Header
        lines.append("# VIPPET Benchmark Results")
        lines.append("")
        lines.append(f"**Benchmark ID:** `{result.get('benchmark_id', 'unknown')}`  ")
        lines.append(f"**Timestamp:** {result.get('timestamp', 'unknown')}  ")
        lines.append(f"**Duration:** {result.get('duration_seconds', 0):.1f}s  ")
        lines.append("")

        # Hardware
        lines.append("## Hardware")
        lines.append("")
        hardware = result.get("hardware", {})
        for family, devices in sorted(hardware.items()):
            lines.append(f"- **{family}:** {', '.join(devices)}")
        lines.append("")

        # Summary
        summary = result.get("summary", {})
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Tests | {summary.get('total', 0)} |")
        lines.append(f"| ✓ Success | {summary.get('success', 0)} |")
        lines.append(f"| ✗ Failed | {summary.get('failed', 0)} |")
        lines.append(f"| ⊘ Skipped | {summary.get('skipped', 0)} |")
        lines.append("")

        # Results table
        lines.append("## Results")
        lines.append("")
        lines.append(
            "| Pipeline | Variant | Streams | Status | Total FPS | Per-Stream FPS |"
            " CPU% avg | GPU Render% avg | GPU Video% avg | NPU% avg | GPU Freq MHz |"
            " GPU Power W | Pkg Power W | CPU Temp C |"
        )
        lines.append(
            "|----------|---------|---------|--------|-----------|----------------|"
            "-----------|-----------------|----------------|----------|--------------|"
            "-------------|-------------|------------|"
        )

        test_cases = result.get("test_cases", [])
        for tc in test_cases:
            result_data = tc.get("result", {}) or {}
            total_fps = result_data.get("total_fps")
            per_stream_fps = result_data.get("per_stream_fps")
            hw = tc.get("hw_metrics", {}) or {}

            status_icon = {
                "success": "✓",
                "failed": "✗",
                "skipped": "⊘",
                "pending": "⏳",
                "running": "▶",
            }.get(tc.get("status", ""), "?")

            def _hw(key: str, fmt: str = ".1f") -> str:
                v = hw.get(key)
                return format(v, fmt) if v is not None else "-"

            lines.append(
                f"| {tc.get('pipeline_name', '')} "
                f"| {tc.get('variant_name', '')} "
                f"| {tc.get('streams', 0)} "
                f"| {status_icon} {tc.get('status', '')} "
                f"| {f'{total_fps:.2f}' if total_fps is not None else '-'} "
                f"| {f'{per_stream_fps:.2f}' if per_stream_fps is not None else '-'} "
                f"| {_hw('cpu_util_pct_avg')} "
                f"| {_hw('gpu_render_util_pct_avg')} "
                f"| {_hw('gpu_video_util_pct_avg')} "
                f"| {_hw('npu_utilization_avg')} "
                f"| {_hw('gpu_freq_mhz_avg', '.0f')} "
                f"| {_hw('gpu_power_w_avg', '.3f')} "
                f"| {_hw('pkg_power_w_avg', '.3f')} "
                f"| {_hw('cpu_temperature_avg', '.0f')} |"
            )

        lines.append("")

        # Failed tests
        failed = [tc for tc in test_cases if tc.get("status") == "failed"]
        if failed:
            lines.append("## Failed Tests")
            lines.append("")
            for tc in failed:
                lines.append(
                    f"### {tc.get('pipeline_name')} ({tc.get('variant_name')}, {tc.get('streams')} streams)"
                )
                lines.append("")
                lines.append(f"**Error:** {tc.get('error', 'Unknown error')}")
                lines.append("")

        # Write file
        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        logger.info("  ✓ Markdown report saved")


class ResultExporter:
    """Main result exporter that handles all formats."""

    def __init__(self, output_dir: Path, formats: list):
        """
        Initialize exporter.

        Args:
            output_dir: Directory to save results
            formats: List of format names ('json', 'csv', 'markdown')
        """
        self.output_dir = output_dir
        self.formats = formats

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Result exporter initialized: {output_dir}")

    def export(self, result: dict[str, Any]):
        """
        Export results in all configured formats.

        Args:
            result: BenchmarkResult dictionary
        """
        benchmark_id = result.get("benchmark_id", "unknown")

        logger.info(f"\n{'=' * 70}")
        logger.info("EXPORTING RESULTS")
        logger.info(f"{'=' * 70}")

        for fmt in self.formats:
            fmt_lower = fmt.lower()

            if fmt_lower == "json":
                output_file = self.output_dir / f"{benchmark_id}.json"
                JSONReporter.save(result, output_file)

            elif fmt_lower == "csv":
                output_file = self.output_dir / f"{benchmark_id}.csv"
                CSVReporter.save(result, output_file)

            elif fmt_lower in ["markdown", "md"]:
                output_file = self.output_dir / f"{benchmark_id}.md"
                MarkdownReporter.save(result, output_file)

            else:
                logger.warning(f"  Unknown format: {fmt}")

        logger.info(f"\n✓ All reports exported to: {self.output_dir}")
