import json
import logging
import os
import pprint
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

logging.basicConfig(level=logging.INFO)


@dataclass
class CollectionReport:
    total_collection_time_seconds: float
    avg_cpu_frequency_mhz: float
    avg_cpu_usage_percent: float
    avg_cpu_temperature_kelvins: float
    avg_memory_usage_percent: float
    avg_package_power_wh: Optional[float] = field(default=None)
    avg_system_temperature_kelvins: Optional[float] = field(default=None)
    avg_gpu_frequency_mhz: Optional[float] = field(default=None)
    avg_gpu_power_wh: Optional[float] = field(default=None)
    avg_gpu_compute_usage_percent: Optional[float] = field(default=None)
    avg_gpu_video_usage_percent: Optional[float] = field(default=None)
    gpu_timestamps: List[float] = field(default_factory=list)  
    gpu_engine_utils: dict = field(default_factory=dict)  


class MetricsCollector:
    def __init__(self):
        pass

    def collect(self):
        raise NotImplementedError("Subclasses should implement this method")

    def stop(self):
        raise NotImplementedError("Subclasses should implement this method")

    def report(self):
        raise NotImplementedError("Subclasses should implement this method")


class WindowsMetricsCollector(MetricsCollector):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("WindowsMetricsCollector")
        self.signal_file = "./.collector-signals/.collector.run"
        self.metrics_file = "./.collector-signals/.collector.out"

    def collect(self):
        with open(self.signal_file, "w") as file:
            self.logger.info(f"Signal to collector posted")

    def stop(self):
        os.remove(self.signal_file)
        self.logger.info(f"Signal to collector removed")

    def report(self) -> CollectionReport:
        self.logger.info(f"Reporting metrics")

        # Read metrics from file
        with open(self.metrics_file, encoding="utf-16", errors="ignore") as file:
            metrics = file.read()

            # Initialize the metrics dictionary
            report = {
                "cpu-frequency-mhz": [],
                "cpu-usage-percent": [],
                "cpu-temperature-kelvins": [],
                "memory-usage-percent": [],
                "package-power-pwh": [],
                "system-temperature-kelvins": [],
                "gpu-frequency-mhz": [],
                "gpu-power-pwh": [],
                "gpu-3d-usage-percent": [],
                "gpu-videodecode-usage-percent": [],
                "timestamps": [],
            }

            # iterate over each line
            for line in metrics.split("\n"):

                # Split the line by space
                segments = line.split(" ")

                # Check that the first segment says metrics
                if segments[0] != "metrics":

                    # Ignore the line otherwise
                    continue

                # The second segment contains the metrics
                metrics = segments[1].split(",")

                # Iterate over the metrics
                for metric in metrics:
                    key, value = metric.split("=")
                    report[key].append(float(value) if value != "null" else None)

                # The third segment contains the timestamp
                timestamp = segments[2]
                report["timestamps"].append(float(timestamp))

            # Compute averages for each metric
            averages = {}

            # Add total collection time
            averages["total-collection-time-seconds"] = (
                report["timestamps"][-1] - report["timestamps"][0]
            )

            for key, values in report.items():
                if key == "timestamps":
                    continue

                # if all the values are None, ignore the metric
                if all(value is None for value in values):
                    averages[f"avg-{key}"] = None
                    continue

                # Convert to Package Power to Wh
                if key == "package-power-pwh":
                    averages[f"avg-package-power-wh"] = round(
                        (sum(values) / len(values)) * 1e-12, 2
                    )
                    continue

                # Convert to GPU Power to Wh
                if key == "gpu-power-pwh":
                    averages[f"avg-gpu-power-wh"] = round(
                        (sum(values) / len(values)) * 1e-12, 2
                    )
                    continue

                averages[f"avg-{key}"] = round(sum(values) / len(values), 2)

            # Log the averages
            self.logger.info(averages)

            # Return the report
            return CollectionReport(
                total_collection_time_seconds=averages["total-collection-time-seconds"],
                avg_cpu_frequency_mhz=averages["avg-cpu-frequency-mhz"],
                avg_cpu_usage_percent=averages["avg-cpu-usage-percent"],
                avg_cpu_temperature_kelvins=averages["avg-cpu-temperature-kelvins"],
                avg_memory_usage_percent=averages["avg-memory-usage-percent"],
                avg_package_power_wh=averages["avg-package-power-wh"],
                avg_system_temperature_kelvins=averages[
                    "avg-system-temperature-kelvins"
                ],
                avg_gpu_frequency_mhz=averages["avg-gpu-frequency-mhz"],
                avg_gpu_power_wh=averages["avg-gpu-power-wh"],
                avg_gpu_compute_usage_percent=averages["avg-gpu-3d-usage-percent"],
                avg_gpu_video_usage_percent=averages[
                    "avg-gpu-videodecode-usage-percent"
                ],
            )


class LinuxMetricsCollector(MetricsCollector):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("LinuxMetricsCollector")
        self.signal_file = "./.collector-signals/.collector.run"
        self.metrics_file = "./.collector-signals/.collector.out"

    def collect(self):
        with open(self.signal_file, "w") as file:
            self.logger.info(f"Signal to collector posted")

    def stop(self):
        os.remove(self.signal_file)
        self.logger.info(f"Signal to collector removed")

    def report(self):
        self.logger.info(f"Reporting metrics")

        averages = {
            "total-collection-time-seconds": None,
            "avg-cpu-frequency-mhz": None,
            "avg-cpu-usage-percent": None,
            "avg-cpu-temperature-kelvins": None,
            "avg-memory-usage-percent": None,
            "avg-package-power-pwh": None,
            "avg-system-temperature-kelvins": None,
        }
        
        gpu_engine_utils = {}

        # Read metrics from file
        with open(self.metrics_file, encoding="utf-8", errors="ignore") as file:
            metrics = file.read()

            # Iterate over each line
            for line in metrics.split("\n"):
                key_value = line.split(": ", 1)  # Split only at the first occurrence of ": "
                if len(key_value) != 2:
                    continue  # Skip invalid lines

                key, value = key_value

                # Match-case statement to parse the metrics
                match key:
                    case "CPU Frequency":
                        averages["avg-cpu-frequency-mhz"] = float(value.split()[0])
                    case "CPU Utilization":
                        averages["avg-cpu-usage-percent"] = float(value.split()[0])
                    case "Memory Utilization":
                        averages["avg-memory-usage-percent"] = float(value.split()[0])
                    case "Package Power":
                        averages["avg-package-power-pwh"] = round(
                            float(value.split()[0]), 3
                        )
                    case "CPU Temperature":
                        averages["avg-cpu-temperature-kelvins"] = (
                            float(value.split()[0]) + 273.15
                        )
                    case "System Temperature":
                        averages["avg-system-temperature-kelvins"] = (
                            float(value.split()[0]) + 273.15
                        )
                    case "GPU Power Usage":
                        averages["avg-gpu-power-wh"] = list(map(float, re.findall(r"[\d.]+", value)))  
                    case "GPU Frequency":
                        averages["avg-gpu-frequency-mhz"] = list(map(float, re.findall(r"[\d.]+", value)))  

                    case "GPU_Timestamps":
                        # Extract timestamps dynamically
                        gpu_timestamps = list(map(float, re.findall(r"[\d.]+", value)))
                    case _:
                        # Handle dynamic GPU engine utilization
                        if key.startswith("gpu_engine_"):
                            engine_name = key  # Keep engine name as-is
                            values = list(map(float, re.findall(r"[\d.]+", value)))

                            # Compute the average for this engine
                            gpu_engine_utils[engine_name] = values

        # Log the averages
        self.logger.info(averages)

        # Return the averages
        return CollectionReport(
            total_collection_time_seconds=averages["total-collection-time-seconds"],
            avg_cpu_frequency_mhz=averages["avg-cpu-frequency-mhz"],
            avg_cpu_usage_percent=averages["avg-cpu-usage-percent"],
            avg_cpu_temperature_kelvins=averages["avg-cpu-temperature-kelvins"],
            avg_memory_usage_percent=averages["avg-memory-usage-percent"],
            avg_package_power_wh=averages["avg-package-power-pwh"],
            avg_system_temperature_kelvins=averages["avg-system-temperature-kelvins"],
            gpu_timestamps=gpu_timestamps,
            gpu_engine_utils = gpu_engine_utils,
            avg_gpu_power_wh = averages["avg-gpu-power-wh"],
            avg_gpu_frequency_mhz = averages["avg-gpu-frequency-mhz"]
        )


class MetricsCollectorFactory:
    @staticmethod
    def get_collector(sysname: str, release: str) -> MetricsCollector:
        if sysname == "Linux" and release.endswith("WSL2"):
            return WindowsMetricsCollector()
        elif sysname == "Linux" and release.startswith("6"):
            return LinuxMetricsCollector()
        else:
            raise ValueError(f"Unsupported System: {sysname} - {release}")


# Example usage
if __name__ == "__main__":
    system = os.uname()
    collector = MetricsCollectorFactory.get_collector(
        sysname=system.sysname, release=system.release
    )
    collector.collect()
    time.sleep(10)
    collector.stop()
    time.sleep(10)
    averages = collector.report()

    # Pretty print the averages
    pprint.pprint(averages)
