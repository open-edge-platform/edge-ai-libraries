#!/usr/bin/python3

# Copyright 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=line-too-long,missing-module-docstring,invalid-name,too-many-locals,too-many-statements

import traceback
import time
import os
import sys
import logging as LOG
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from flask import Flask, Response
from enum import Enum, unique
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest
)

KB = 1024

def load_npu_monitor():
    """Dynamically load monitor classes from standalone npu-monitor-tool.py."""
    module_path = Path(__file__).resolve().parent / 'npu-monitor-tool.py'
    spec = spec_from_file_location('npu_monitor_tool', module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Unable to load monitor module from {module_path}')

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NpuMonitor

NpuMonitor = load_npu_monitor()

# NPU Monitor
npu_mon = NpuMonitor()
pu = npu_mon.get_pmt_telemetry()
if pu is None:
    print('Failed to setup NPU monitor')
    sys.exit(1)

pciid = npu_mon.read_pciid()

# Prometheus data source registry
registries = {}
metrics_owner = f'npu'
registry, metrics = registries.setdefault(
                        metrics_owner, (CollectorRegistry(), {}))

# Get initial value for interval-related metrics (utilization and power)
curr_time_ms = 0
prev_time_ms = time.time_ns() // 1_000_000
prev_busy_time = npu_mon.read_busy_time()
pu.update_buffer()
prev_energy = pu.get_npu_energy()
prev_mem_bandwidth_mb = pu.get_noc_bandwidth()
prev_mem_bandwidth_ts = time.monotonic()

@unique
class PromMetric(Enum):
    npu_monitor_temperature = ('npu_monitor_temperature', 'NPU Temperature [°C]') # nopep8
    npu_monitor_freq_hz = ('npu_monitor_freq_hz', 'DPU Frequency [Hz]') # nopep8
    npu_memory_util = ('npu_memory_util', 'NPU Memory Utilization [MB]') # nopep8
    npu_memory_bandwidth =('npu_memory_bandwidth', 'NPU DDR Average Bandwidth [MB/s]') # nopep8
    npu_util = ('npu_util', 'NPU Utilization [%]') # nopep8
    npu_monitor_power = ('npu_monitor_power', 'NPU Power Consumption [Watts]') # nopep8
    npu_tile_config = ('npu_tile_config', 'NPU Tile Configuration') # nopep8

    def __new__(cls, name, desc=None, ext_labelnames=[]):
        obj = object.__new__(cls)
        obj._value_ = name
        obj.desc = f'{name}_desc' if desc is None else desc
        obj.ext_labelnames = ext_labelnames
        return obj

class Metric:
    def __init__(self, prom_metric: PromMetric) -> None:
        self.prom_metric = prom_metric

metrics_map = {
    'NPU_TEMPERATURE': Metric(PromMetric.npu_monitor_temperature),
    'NPU_FREQUENCY': Metric(PromMetric.npu_monitor_freq_hz),
    'NPU_MEM_UTIL': Metric(PromMetric.npu_memory_util),
    'NPU_MEM_BANDWIDTH': Metric(PromMetric.npu_memory_bandwidth),
    'NPU_UTIL': Metric(PromMetric.npu_util),
    'NPU_POWER': Metric(PromMetric.npu_monitor_power),
    'NPU_TILE_CFG':  Metric(PromMetric.npu_tile_config),
}

def process_npu_temperature():
    metric = metrics_map['NPU_TEMPERATURE']
    metric_name = metric.prom_metric.name
    metric_desc = metric.prom_metric.desc
    all_labelnames = ['dev_id']
    all_labelvalues = [f'{pciid}']

    val = pu.get_npu_temperature()
    if metric_name not in metrics:
        metrics[metric_name] = Gauge(metric_name, metric_desc,
                                    labelnames=all_labelnames,
                                    registry=registry)
        metrics[metric_name].labels(*all_labelvalues).set(val)
    else:
        metrics[metric_name].labels(*all_labelvalues).set(val)

def process_npu_frequency():
    metric = metrics_map['NPU_FREQUENCY']
    metric_name = metric.prom_metric.name
    metric_desc = metric.prom_metric.desc
    all_labelnames = ['dev_id']
    all_labelvalues = [f'{pciid}']

    val = pu.get_display_freq_hz()
    if metric_name not in metrics:
        metrics[metric_name] = Gauge(metric_name, metric_desc,
                                    labelnames=all_labelnames,
                                    registry=registry)
        metrics[metric_name].labels(*all_labelvalues).set(val)
    else:
        metrics[metric_name].labels(*all_labelvalues).set(val)

def process_npu_mem_util():
    metric = metrics_map['NPU_MEM_UTIL']
    metric_name = metric.prom_metric.name
    metric_desc = metric.prom_metric.desc
    all_labelnames = ['dev_id']
    all_labelvalues = [f'{pciid}']

    mem_util = npu_mon.read_mem_util()
    try:
        mem_util_mb = int(mem_util) / KB / KB
    except (TypeError, ValueError) as err:
        LOG.warning('Failed to parse memory utilization: %s', err)
        mem_util_mb = 0

    if metric_name not in metrics:
        metrics[metric_name] = Gauge(metric_name, metric_desc,
                                    labelnames=all_labelnames,
                                    registry=registry)
        metrics[metric_name].labels(*all_labelvalues).set(mem_util_mb)
    else:
        metrics[metric_name].labels(*all_labelvalues).set(mem_util_mb)

def process_npu_mem_bandwidth():
    global prev_mem_bandwidth_mb
    global prev_mem_bandwidth_ts

    metric = metrics_map['NPU_MEM_BANDWIDTH']
    metric_name = metric.prom_metric.name
    metric_desc = metric.prom_metric.desc
    all_labelnames = ['dev_id']
    all_labelvalues = [f'{pciid}']

    try:
        curr_mem_bandwidth_mb = pu.get_noc_bandwidth()
    except (TypeError, ValueError) as err:
        LOG.warning('Failed to parse memory bandwidth: %s', err)
        curr_mem_bandwidth_mb = 0

    curr_mem_bandwidth_ts = time.monotonic()
    delta_ts = curr_mem_bandwidth_ts - prev_mem_bandwidth_ts

    if prev_mem_bandwidth_mb is None or curr_mem_bandwidth_mb is None or delta_ts <= 0:
        bandwidth_mbps = 0.0
    else:
        delta_mem_bandwidth_mb = curr_mem_bandwidth_mb - prev_mem_bandwidth_mb
        bandwidth_mbps = max(0.0, delta_mem_bandwidth_mb / delta_ts)

    prev_mem_bandwidth_mb = curr_mem_bandwidth_mb
    prev_mem_bandwidth_ts = curr_mem_bandwidth_ts

    if metric_name not in metrics:
        metrics[metric_name] = Gauge(metric_name, metric_desc,
                                    labelnames=all_labelnames,
                                    registry=registry)
        metrics[metric_name].labels(*all_labelvalues).set(bandwidth_mbps)
    else:
        metrics[metric_name].labels(*all_labelvalues).set(bandwidth_mbps)

def process_npu_utilization():
    global curr_time_ms
    global prev_time_ms
    global prev_busy_time

    metric = metrics_map['NPU_UTIL']
    metric_name = metric.prom_metric.name
    metric_desc = metric.prom_metric.desc
    all_labelnames = ['dev_id']
    all_labelvalues = [f'{pciid}']

    curr_busy_time = npu_mon.read_busy_time()
    if prev_busy_time is None or curr_busy_time is None:
        utilization = 0
    else:
        # delta is in micro-seconds, interval is in milli-seconds
        delta_busy_time = curr_busy_time - prev_busy_time
        interval_us = (curr_time_ms - prev_time_ms) * 1000
        if interval_us <= 0:
            utilization = 0
        else:
            utilization = min(100, int(100 * delta_busy_time / interval_us))

        prev_busy_time = curr_busy_time

    if metric_name not in metrics:
        metrics[metric_name] = Gauge(metric_name, metric_desc,
                                    labelnames=all_labelnames,
                                    registry=registry)
        metrics[metric_name].labels(*all_labelvalues).set(utilization)
    else:
        metrics[metric_name].labels(*all_labelvalues).set(utilization)

def process_npu_power():
    global curr_time_ms
    global prev_time_ms
    global prev_energy

    metric = metrics_map['NPU_POWER']
    metric_name = metric.prom_metric.name
    metric_desc = metric.prom_metric.desc
    all_labelnames = ['dev_id']
    all_labelvalues = [f'{pciid}']

    curr_energy = pu.get_npu_energy()
    if prev_energy is None or curr_energy is None:
        power = 0
    else:
        interval_ms = curr_time_ms - prev_time_ms
        if interval_ms <= 0:
            power = 0
        else:
            power = (curr_energy - prev_energy) / (interval_ms * 1e-3)

        prev_energy = curr_energy

    if metric_name not in metrics:
        metrics[metric_name] = Gauge(metric_name, metric_desc,
                                    labelnames=all_labelnames,
                                    registry=registry)
        metrics[metric_name].labels(*all_labelvalues).set(power)
    else:
        metrics[metric_name].labels(*all_labelvalues).set(power)

def process_npu_tile_config():
    metric = metrics_map['NPU_TILE_CFG']
    metric_name = metric.prom_metric.name
    metric_desc = metric.prom_metric.desc
    all_labelnames = ['dev_id']
    all_labelvalues = [f'{pciid}']
    val = pu.get_tile_config()
    if metric_name not in metrics:
        metrics[metric_name] = Gauge(metric_name, metric_desc,
                                    labelnames=all_labelnames,
                                    registry=registry)
        metrics[metric_name].labels(*all_labelvalues).set(val)
    else:
        metrics[metric_name].labels(*all_labelvalues).set(val)

def tidy_response(resp):
    resp_str = resp.decode('UTF-8')
    tidy_resp = []
    is_comment = False
    for line in resp_str.splitlines():
        if not line.startswith('#'):
            if line not in tidy_resp:
                tidy_resp.append(line)
                is_comment = False
        else:
            if is_comment == False:
                tidy_resp.append('\n' + line)
                is_comment = True
            else:
                tidy_resp.append(line)

    return '\n'.join(tidy_resp)

def get_metrics():
    global curr_time_ms
    global prev_time_ms

    try:
        curr_time_ms = time.time_ns() // 1_000_000
        pu.update_buffer()

        process_npu_temperature()
        process_npu_frequency()
        process_npu_mem_util()
        process_npu_mem_bandwidth()
        process_npu_utilization()
        process_npu_power()
        process_npu_tile_config()

        prev_time_ms = curr_time_ms

        resp = generate_latest(registry)
        return tidy_response(resp)

    except Exception as e:
        traceback.print_exc()
        return "#nodata: due to unexpected failure", 500

def export_metrics():
    result = get_metrics()

    # Handle (body, status) or just body
    if isinstance(result, tuple):
        body, status = result
        body = body + '\n'
    else:
        body, status = result + '\n', 200

    return Response(body, status=status, content_type='text/plain')

def hello_world():
    body = "NPU telemetry source for Prometheus\n"
    status = 200
    return Response(body, status=status, content_type='text/plain')

app = Flask(__name__)

app.add_url_rule(
    '/', view_func=hello_world, methods=['GET'])

app.add_url_rule(
    '/metrics', view_func=export_metrics, methods=['GET'])

