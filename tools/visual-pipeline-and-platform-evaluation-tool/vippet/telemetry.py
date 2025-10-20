from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from chart import ChartType

METRICS_FILE_PATH = "/home/dlstreamer/vippet/.collector-signals/metrics.txt"
FPS_FILE_PATH = "/home/dlstreamer/vippet/.collector-signals/fps.txt"


class Telemetry:
    def __init__(self, charts):
        self.charts = charts

    def generate_stream_data(self):
        new_x = datetime.now()

        # Read metrics once
        metrics = self.read_latest_metrics()

        # Read FPS once
        latest_fps = 0
        try:
            with open(FPS_FILE_PATH, "r") as fps_file:
                lines = [line.strip() for line in fps_file.readlines()[-500:]]
                latest_fps = float(lines[-1])
        except (FileNotFoundError, IndexError):
            latest_fps = 0

        figs = []
        for chart in self.charts:
            new_y = 0

            if chart.type == ChartType.PIPELINE_THROUGHPUT:
                new_y = latest_fps
            elif (
                chart.type == ChartType.CPU_FREQUENCY
                and metrics["cpu_freq"] is not None
            ):
                new_y = metrics["cpu_freq"]
            elif (
                chart.type == ChartType.CPU_UTILIZATION
                and metrics["cpu_user"] is not None
            ):
                new_y = metrics["cpu_user"]
            elif (
                chart.type == ChartType.CPU_TEMPERATURE
                and metrics["core_temp"] is not None
            ):
                new_y = metrics["core_temp"]
            elif (
                chart.type == ChartType.MEMORY_UTILIZATION
                and metrics["mem_used_percent"] is not None
            ):
                new_y = metrics["mem_used_percent"]
            elif chart.type == ChartType.DGPU_POWER and chart.gpu_id is not None:
                metrics_dict = {
                    "Package Power": metrics.get(f"gpu_package_power_{chart.gpu_id}"),
                    "Total Power": metrics.get(f"gpu_power_{chart.gpu_id}"),
                }
                figs.append(self.update_multi_metric_chart(chart, metrics_dict, new_x))
                continue
            elif chart.type == ChartType.DGPU_FREQUENCY and chart.gpu_id is not None:
                freq = metrics.get(f"gpu_freq_{chart.gpu_id}")
                if freq is not None:
                    new_y = freq
            elif (
                chart.type == ChartType.DGPU_ENGINE_UTILIZATION
                and chart.gpu_id is not None
            ):
                metrics_dict = {
                    "Render": metrics.get(f"gpu_render_{chart.gpu_id}"),
                    "Video Enhance": metrics.get(f"gpu_ve_{chart.gpu_id}"),
                    "Video": metrics.get(f"gpu_video_{chart.gpu_id}"),
                    "Copy": metrics.get(f"gpu_copy_{chart.gpu_id}"),
                    "Compute": metrics.get(f"gpu_compute_{chart.gpu_id}"),
                }
                figs.append(self.update_multi_metric_chart(chart, metrics_dict, new_x))
                continue
            elif chart.type == ChartType.IGPU_POWER and chart.gpu_id is not None:
                metrics_dict = {
                    "Package Power": metrics.get(f"gpu_package_power_{chart.gpu_id}"),
                    "Total Power": metrics.get(f"gpu_power_{chart.gpu_id}"),
                }
                figs.append(self.update_multi_metric_chart(chart, metrics_dict, new_x))
                continue
            elif chart.type == ChartType.IGPU_FREQUENCY and chart.gpu_id is not None:
                freq = metrics.get(f"gpu_freq_{chart.gpu_id}")
                if freq is not None:
                    new_y = freq
            elif (
                chart.type == ChartType.IGPU_ENGINE_UTILIZATION
                and chart.gpu_id is not None
            ):
                metrics_dict = {
                    "Render": metrics.get(f"gpu_render_{chart.gpu_id}"),
                    "Video Enhance": metrics.get(f"gpu_ve_{chart.gpu_id}"),
                    "Video": metrics.get(f"gpu_video_{chart.gpu_id}"),
                    "Copy": metrics.get(f"gpu_copy_{chart.gpu_id}"),
                    "Compute": metrics.get(f"gpu_compute_{chart.gpu_id}"),
                }
                figs.append(self.update_multi_metric_chart(chart, metrics_dict, new_x))
                continue

            new_row = pd.DataFrame({"x": [new_x], "y": [new_y]})
            # Only include non-empty DataFrames in concat to avoid FutureWarning
            if chart.df.empty:
                chart.df = new_row
            else:
                chart.df = pd.concat([chart.df, new_row], ignore_index=True).tail(50)

            chart.fig.data = []  # clear previous trace
            chart.fig.add_trace(
                go.Scatter(x=chart.df["x"], y=chart.df["y"], mode="lines")
            )

            figs.append(chart.fig)

        return figs

    def read_latest_metrics(self):
        # Get all gpu_ids present in charts
        gpu_ids_in_charts = set(
            chart.gpu_id for chart in self.charts if chart.gpu_id is not None
        )

        # Prepare metrics map with all keys set to None
        metrics: dict[str, Optional[float]] = {
            "cpu_user": None,
            "mem_used_percent": None,
            "core_temp": None,
            "cpu_freq": None,
        }
        # For each GPU id, add all relevant metrics keys
        gpu_metric_keys = [
            "gpu_package_power",
            "gpu_power",
            "gpu_freq",
            "gpu_render",
            "gpu_ve",
            "gpu_video",
            "gpu_copy",
            "gpu_compute",
        ]
        for gpu_id in gpu_ids_in_charts:
            for key in gpu_metric_keys:
                metrics[f"{key}_{gpu_id}"] = None

        try:
            with open(METRICS_FILE_PATH, "r") as metrics_file:
                lines = [line.strip() for line in metrics_file.readlines()[-500:]]
        except FileNotFoundError:
            return metrics

        for line in reversed(lines):
            line = self.normalize_engine_names(line)

            # CPU metrics
            if metrics["cpu_user"] is None and "cpu" in line:
                parts = line.split()
                if len(parts) > 1:
                    for field in parts[1].split(","):
                        if field.startswith("usage_user="):
                            try:
                                metrics["cpu_user"] = float(field.split("=")[1])
                            except (ValueError, IndexError):
                                pass

            if metrics["mem_used_percent"] is None and "mem" in line:
                parts = line.split()
                if len(parts) > 1:
                    for field in parts[1].split(","):
                        if field.startswith("used_percent="):
                            try:
                                metrics["mem_used_percent"] = float(field.split("=")[1])
                            except (ValueError, IndexError):
                                pass

            if metrics["core_temp"] is None and "temp" in line:
                parts = line.split()
                if len(parts) > 1:
                    for field in parts[1].split(","):
                        if "temp" in field:
                            try:
                                metrics["core_temp"] = float(field.split("=")[1])
                            except (ValueError, IndexError):
                                pass

            if metrics["cpu_freq"] is None and "cpu_frequency_avg" in line:
                try:
                    parts = [part for part in line.split() if "frequency=" in part]
                    if parts:
                        metrics["cpu_freq"] = float(parts[0].split("=")[1])
                except (ValueError, IndexError):
                    pass

            # GPU metrics for all detected gpu_ids
            for gpu_id in gpu_ids_in_charts:
                id_str = f"gpu_id={gpu_id}"
                # Package Power
                key = f"gpu_package_power_{gpu_id}"
                if metrics[key] is None and "pkg_cur_power" in line and id_str in line:
                    parts = line.split()
                    try:
                        metrics[key] = float(parts[1].split("=")[1])
                    except (ValueError, IndexError):
                        pass
                # Total Power
                key = f"gpu_power_{gpu_id}"
                if metrics[key] is None and "gpu_cur_power" in line and id_str in line:
                    parts = line.split()
                    try:
                        metrics[key] = float(parts[1].split("=")[1])
                    except (ValueError, IndexError):
                        pass
                # Frequency
                key = f"gpu_freq_{gpu_id}"
                if metrics[key] is None and "gpu_frequency" in line and id_str in line:
                    for part in line.split():
                        if part.startswith("value="):
                            try:
                                metrics[key] = float(part.split("=")[1])
                            except (ValueError, IndexError):
                                pass
                # Render
                key = f"gpu_render_{gpu_id}"
                if metrics[key] is None and "engine=render" in line and id_str in line:
                    for part in line.split():
                        if part.startswith("usage="):
                            try:
                                metrics[key] = float(part.split("=")[1])
                            except (ValueError, IndexError):
                                pass
                # Copy
                key = f"gpu_copy_{gpu_id}"
                if metrics[key] is None and "engine=copy" in line and id_str in line:
                    for part in line.split():
                        if part.startswith("usage="):
                            try:
                                metrics[key] = float(part.split("=")[1])
                            except (ValueError, IndexError):
                                pass
                # Video Enhance
                key = f"gpu_ve_{gpu_id}"
                if (
                    metrics[key] is None
                    and "engine=video-enhance" in line
                    and id_str in line
                ):
                    for part in line.split():
                        if part.startswith("usage="):
                            try:
                                metrics[key] = float(part.split("=")[1])
                            except (ValueError, IndexError):
                                pass
                # Video
                key = f"gpu_video_{gpu_id}"
                if (
                    metrics[key] is None
                    and "engine=video" in line
                    and "engine=video-enhance" not in line
                    and id_str in line
                ):
                    for part in line.split():
                        if part.startswith("usage="):
                            try:
                                metrics[key] = float(part.split("=")[1])
                            except (ValueError, IndexError):
                                pass
                # Compute
                key = f"gpu_compute_{gpu_id}"
                if metrics[key] is None and "engine=compute" in line and id_str in line:
                    for part in line.split():
                        if part.startswith("usage="):
                            try:
                                metrics[key] = float(part.split("=")[1])
                            except (ValueError, IndexError):
                                pass

            # Early exit if all metrics are filled
            if all(v is not None for v in metrics.values()):
                break

        return metrics

    @staticmethod
    def normalize_engine_names(line: str) -> str:
        """
        Class names for XE drivers: https://github.com/ulissesf/qmassa/blob/v1.0.1/src/drm_drivers/xe.rs#L79-L92
        are different from those used in i915 drivers: https://github.com/ulissesf/qmassa/blob/v1.0.1/src/drm_drivers/i915.rs#L100-L113
        Normalize them to the i915 names.
        """
        return (
            line.replace("engine=rcs", "engine=render")
            .replace("engine=bcs", "engine=copy")
            .replace("engine=ccs", "engine=compute")
            .replace("engine=vcs", "engine=video")
            .replace("engine=vecs", "engine=video-enhance")
        )

    @staticmethod
    def update_multi_metric_chart(chart, metrics, new_x):
        """
        Update chart DataFrame and figure for charts with multiple metrics.
        """
        if chart.df.empty:
            chart.df = pd.DataFrame(columns=pd.Index(["x"] + list(metrics.keys())))
        new_row = pd.DataFrame([{"x": new_x, **metrics}])
        # Only include non-empty DataFrames in concat to avoid FutureWarning
        if chart.df.empty:
            chart.df = new_row
        else:
            chart.df = pd.concat([chart.df, new_row], ignore_index=True).tail(50)
        chart.fig.data = []
        for key in metrics.keys():
            chart.fig.add_trace(
                go.Scatter(x=chart.df["x"], y=chart.df[key], mode="lines", name=key)
            )
        return chart.fig
