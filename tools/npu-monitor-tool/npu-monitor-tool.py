#!/usr/bin/python3

# Copyright 2025 Intel Corporation
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

import argparse
import os
import sys
from time import sleep
import time as time_module
import logging as LOG
import subprocess # nosec B404
import enum
from pathlib import Path
import shutil
from datetime import datetime
from core.utils import fdump
from core.main import NpuMonitor

KB = 1024
MB_TO_GB = 1024
DEFAULT_INTERVAL_MS = 200
CLEAR_CMD = shutil.which('clear')

def logging_setup(args) -> None:
    """Configure colored logging output."""
    log_format = '%(levelname)s: %(message)s'
    LOG.addLevelName(LOG.DEBUG, '\033[1;36mDEBUG\033[1;0m')
    LOG.addLevelName(LOG.INFO, '\033[1;32mINFO\033[1;0m')
    LOG.addLevelName(LOG.ERROR, '\033[1;31mERROR\033[1;0m')

    log_level = LOG.DEBUG if args.verbose else LOG.INFO

    LOG.basicConfig(format=log_format, level=log_level)

def main(): # pylint: disable=too-many-branches
    parser = argparse.ArgumentParser(
        prog='Intel NPU System Monitoring Tool',
        description="""
        A comprehensive tool for monitoring Intel Neural Processing Unit (NPU) performance metrics.

        This tool provides real-time information about the NPU, including:
        - Power consumption (in watts)
        - Processing unit utilization (percentage)
        - Memory utilization (MB/GB)
        - Operating frequency (Hz)
        - Temperature readings (°C)
        - Memory bandwidth (MB/GB)
        - Tile configuration

        Use the interval option to continuously monitor NPU status, or run once for a snapshot.
        Use the --csv flag to output data in CSV format for easy parsing and analysis.
        """)

    parser.add_argument('-i', '--interval', metavar='<msec>', type=float, help='Probing interval in milliseconds.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output.')
    parser.add_argument('--csv', action='store_true', help='Output data in CSV format into the output folder with timestamped filename.')
    args = parser.parse_args()

    logging_setup(args)

    npu_mon = NpuMonitor()
    pu = npu_mon.get_pmt_telemetry()
    if pu is None:
        LOG.error('Failed to setup NPU monitor')
        parser.print_help()
        sys.exit(1)

    pciid = npu_mon.read_pciid()
    driver_version = npu_mon.read_driver_version()
    fw_version = npu_mon.read_fw_version()

    pu.update_buffer()
    prev_busy_time = npu_mon.read_busy_time()
    prev_energy = pu.get_npu_energy()
    interval = args.interval if args.interval else DEFAULT_INTERVAL_MS
    prev_bandwidth = pu.get_noc_bandwidth()
    prev_bandwidth_ts = time_module.monotonic()

    csv_file = None
    csv_file_path = None
    try:
        if args.csv:
            output_dir = 'npu_output'
            try:
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)
            except OSError as e:
                LOG.error('Failed to create output directory: %s', e)
                sys.exit(1)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_file_path = os.path.join(output_dir, f'npu_{timestamp}.csv')
            csv_file = open(csv_file_path, 'w', encoding='utf-8')
            csv_file.write('timestamp,power,frequency,bandwidth,tile_config,temperature,utilization,memory_usage\n')
            LOG.info(f'CSV output enabled. Writing to: {csv_file_path}')

        while True:
            sleep(interval * 1e-3)
            curr_busy_time = npu_mon.read_busy_time()
            if (args.interval or args.csv) and CLEAR_CMD:
                subprocess.run([CLEAR_CMD], check=False) # nosec B603

            if prev_busy_time is None or curr_busy_time is None:
                utilization = 0
                LOG.warning('read_busy_time() returned None; setting utilization to 0.')
            else:
                # delta is in microseconds, interval is in milliseconds
                delta_us = curr_busy_time - prev_busy_time
                interval_us = interval * 1000
                if interval_us <= 0:
                    utilization = 0
                    LOG.warning('Interval is zero or negative; setting utilization to 0 to avoid division by zero.')
                else:
                    utilization = min(100, int(100 * delta_us / interval_us))

            mem_util_raw = npu_mon.read_mem_util()
            mem_util: float | None = None
            mem_util_unit = '--'

            # read_mem_util() is expected to return a numeric value (in KB). Be defensive
            # to avoid invalid operations when it returns None or a non-numeric value.
            try:
                mem_util_raw_num = float(mem_util_raw) if mem_util_raw is not None else 0.0
            except (TypeError, ValueError):
                mem_util_raw_num = 0.0

            if mem_util_raw_num > 0:
                mem_util_mb = mem_util_raw_num / KB / KB
                if mem_util_mb > MB_TO_GB:
                    mem_util = mem_util_mb / MB_TO_GB
                    mem_util_unit = 'GB'
                else:
                    mem_util = mem_util_mb
                    mem_util_unit = 'MB'

            if mem_util is None:
                mem_util_str = f'{"N/A":>31} [--]'
            else:
                mem_util_str = f'{mem_util:>31.2f} [{mem_util_unit}]'

            pu.update_buffer()

            curr_energy = pu.get_npu_energy()
            power = (curr_energy - prev_energy) / (interval * 1e-3)
            prev_energy = curr_energy
            freq_mhz = pu.get_freq()
            freq_hz = pu.get_display_freq_hz()
            tile_config = pu.get_tile_config()

            temp = pu.get_npu_temperature()

            curr_bandwidth = pu.get_noc_bandwidth()
            curr_bandwidth_ts = time_module.monotonic()
            bandwidth_delta = curr_bandwidth - prev_bandwidth
            dt_s = curr_bandwidth_ts - prev_bandwidth_ts

            # Guard against clock quirks and counter resets/wrap.
            if dt_s <= 0:
                bandwidth_mbps = 0.0
            else:
                bandwidth_mbps = max(0.0, bandwidth_delta / dt_s)

            if bandwidth_mbps > MB_TO_GB:
                bandwidth = bandwidth_mbps / MB_TO_GB
                bw_unit = 'GB/s'
            else:
                bandwidth = bandwidth_mbps
                bw_unit = 'MB/s'

            if csv_file:
                timestamp = int(time_module.time())
                csv_file.write(f'{timestamp},{power:.3f},{freq_hz:.0f},{bandwidth:.3f},{tile_config},{temp},{utilization},{mem_util_mb:.2f}\n')
                csv_file.flush()

            print( '+-----------------------------------------------------------------------------------------------+')
            print(f'| INTEL NPU Device: {pciid:>6} | version: {driver_version:>57} |')
            print(f'| Firmware version: {fw_version[:75]:<75} |')
            print(f'| {fw_version[75:]:<94}|')
            print( '+===============================================================================================+')
            print( '|       Power Usage        |      DPU Freq        | NPU DDR Average Bandwidth |    Tile Conf    |')
            print(f'|{round(power, 3):>21} [W] |{round(freq_hz):>16} [Hz] | {round(bandwidth, 3):>18.2f} [{bw_unit}] | {tile_config:>15} |')
            print( '+===============================================================================================+')
            print( '|       NPU Temperature    |       NPU Utilization       |      Memory Usage                    |')
            print(f'| {temp:>19} [°C] | {utilization:>26}% | {mem_util_str} |')
            print( '+-----------------------------------------------------------------------------------------------+')
            prev_busy_time = curr_busy_time
            prev_bandwidth = curr_bandwidth
            prev_bandwidth_ts = curr_bandwidth_ts

            if not args.interval:
                break
    finally:
        if csv_file:
            csv_file.close()


if __name__ == '__main__':
    main()
