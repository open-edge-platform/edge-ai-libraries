from typing import List
from enum import Enum, auto

import pandas as pd
import plotly.graph_objects as go


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
    def __init__(self, title: str, y_label: str, type_: ChartType):
        self.title = title
        self.y_label = y_label
        self.type = type_
        self.df = pd.DataFrame(columns=["x", "y"])
        self.fig = self.create_empty_fig()

    def create_empty_fig(self):
        fig = go.Figure()
        fig.update_layout(
            title=self.title, xaxis_title="Time", yaxis_title=self.y_label
        )
        return fig

    def reset(self):
        self.df = pd.DataFrame(columns=["x", "y"])
        self.fig = self.create_empty_fig()


def create_charts(devices) -> List[Chart]:
    has_igpu = any("iGPU" in name or "igpu" in name for name, _ in devices)
    has_dgpu = any(
        "dGPU" in name or "dgpu" in name or "Discrete" in name or "discrete" in name
        for name, _ in devices
    )

    all_chart_titles = [
        "Pipeline Throughput [FPS]",
        "CPU Utilization [%]",
        "Integrated GPU Engine Utilization [%]",
        "Discrete GPU Engine Utilization [%]",
        "Memory Utilization [%]",
        "Integrated GPU Power Usage [W] (Package & Total)",
        "Integrated GPU Frequency [MHz]",
        "Discrete GPU Power Usage [W] (Package & Total)",
        "Discrete GPU Frequency [MHz]",
        "CPU Frequency [KHz]",
        "CPU Temperature [C°]",
    ]
    all_y_labels = [
        "Throughput",
        "Utilization",
        "Utilization",
        "Utilization",
        "Utilization",
        "Power",
        "Frequency",
        "Power",
        "Frequency",
        "Frequency",
        "Temperature",
    ]
    all_types = [
        ChartType.PIPELINE_THROUGHPUT,
        ChartType.CPU_UTILIZATION,
        ChartType.IGPU_ENGINE_UTILIZATION,
        ChartType.DGPU_ENGINE_UTILIZATION,
        ChartType.MEMORY_UTILIZATION,
        ChartType.IGPU_POWER,
        ChartType.IGPU_FREQUENCY,
        ChartType.DGPU_POWER,
        ChartType.DGPU_FREQUENCY,
        ChartType.CPU_FREQUENCY,
        ChartType.CPU_TEMPERATURE,
    ]

    igpu_indices = [2, 5, 6]
    dgpu_indices = [3, 7, 8]

    indices_to_remove = []
    if not has_igpu:
        indices_to_remove += igpu_indices
    if not has_dgpu:
        indices_to_remove += dgpu_indices

    chart_titles = [
        t for i, t in enumerate(all_chart_titles) if i not in indices_to_remove
    ]
    y_labels = [y for i, y in enumerate(all_y_labels) if i not in indices_to_remove]
    types = [t for i, t in enumerate(all_types) if i not in indices_to_remove]

    return [
        Chart(chart_titles[i], y_labels[i], types[i]) for i in range(len(chart_titles))
    ]
