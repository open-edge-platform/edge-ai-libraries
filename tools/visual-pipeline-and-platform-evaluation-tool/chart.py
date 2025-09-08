from typing import List
from enum import Enum, auto
import logging

import pandas as pd
import plotly.graph_objects as go

from device import DeviceFamily, DeviceInfo, DeviceType

logger = logging.getLogger("chart")


class ChartType(Enum):
    PIPELINE_THROUGHPUT = auto()
    CPU_UTILIZATION = auto()
    IGPU_ENGINE_UTILIZATION = auto()
    DGPU_ENGINE_UTILIZATION = auto()
    MEMORY_UTILIZATION = auto()
    IGPU_POWER = auto()
    IGPU_FREQUENCY = auto()
    DGPU_POWER = auto()
    DGPU_FREQUENCY = auto()
    CPU_FREQUENCY = auto()
    CPU_TEMPERATURE = auto()


# Chart class to manage individual charts
class Chart:
    def __init__(
        self, title: str, y_label: str, type_: ChartType, gpu_id: int | None = None
    ):
        self.title = title
        self.y_label = y_label
        self.type = type_
        self.gpu_id = gpu_id
        self.df = pd.DataFrame(columns=pd.Index(["x", "y"]))
        self.fig = self.create_empty_fig()

    def create_empty_fig(self):
        fig = go.Figure()
        fig.update_layout(
            title=self.title, xaxis_title="Time", yaxis_title=self.y_label
        )
        return fig

    def reset(self):
        self.df = pd.DataFrame(columns=pd.Index(["x", "y"]))
        self.fig = self.create_empty_fig()


def create_charts(devices: List[DeviceInfo]) -> List[Chart]:
    logger.debug("Devices information:")
    for device in devices:
        logger.debug(f"\tDevice: {device}")

    # FPS and CPU Utilization charts
    charts: List[Chart] = [
        Chart("Pipeline Throughput [FPS]", "Throughput", ChartType.PIPELINE_THROUGHPUT),
        Chart("CPU Utilization [%]", "Utilization", ChartType.CPU_UTILIZATION),
    ]

    # Find all GPUs
    igpus = [
        d
        for d in devices
        if d.device_family == DeviceFamily.GPU
        and d.device_type == DeviceType.INTEGRATED
    ]
    dgpus = [
        d
        for d in devices
        if d.device_family == DeviceFamily.GPU and d.device_type == DeviceType.DISCRETE
    ]

    # Integrated GPU Engine Utilization charts
    for igpu in igpus:
        charts.append(
            Chart(
                f"{igpu.device_name} Engine Utilization [%] (integrated)",
                "Utilization",
                ChartType.IGPU_ENGINE_UTILIZATION,
                gpu_id=igpu.gpu_id,
            )
        )

    # Discrete GPU Engine Utilization charts
    for dgpu in dgpus:
        charts.append(
            Chart(
                f"{dgpu.device_name} Engine Utilization [%] (discrete)",
                "Utilization",
                ChartType.DGPU_ENGINE_UTILIZATION,
                gpu_id=dgpu.gpu_id,
            )
        )

    charts.append(
        Chart("Memory Utilization [%]", "Utilization", ChartType.MEMORY_UTILIZATION)
    )

    # Integrated GPU Power/Freq charts
    for igpu in igpus:
        charts.append(
            Chart(
                f"{igpu.device_name} Power Usage [W] (Package & Total) (integrated)",
                "Power",
                ChartType.IGPU_POWER,
                gpu_id=igpu.gpu_id,
            )
        )
        charts.append(
            Chart(
                f"{igpu.device_name} Frequency [MHz] (integrated)",
                "Frequency",
                ChartType.IGPU_FREQUENCY,
                gpu_id=igpu.gpu_id,
            )
        )

    # Discrete GPU Power/Freq charts
    for dgpu in dgpus:
        charts.append(
            Chart(
                f"{dgpu.device_name} Power Usage [W] (Package & Total) (discrete)",
                "Power",
                ChartType.DGPU_POWER,
                gpu_id=dgpu.gpu_id,
            )
        )
        charts.append(
            Chart(
                f"{dgpu.device_name} Frequency [MHz] (discrete)",
                "Frequency",
                ChartType.DGPU_FREQUENCY,
                gpu_id=dgpu.gpu_id,
            )
        )

    # CPU Frequency & Temperature charts
    charts.append(Chart("CPU Frequency [KHz]", "Frequency", ChartType.CPU_FREQUENCY))
    charts.append(
        Chart("CPU Temperature [C°]", "Temperature", ChartType.CPU_TEMPERATURE)
    )

    return charts
