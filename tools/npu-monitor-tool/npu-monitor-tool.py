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
import shlex
import enum
from pathlib import Path
import shutil
from typing import Optional
from datetime import datetime


def fdump(path: str) -> str:
    """Read and return the contents of a file, with error handling."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        LOG.error('File not found: %s', path)
        sys.exit(1)
    except PermissionError:
        LOG.error('Permission denied reading: %s', path)
        sys.exit(1)
    except Exception as e:
        LOG.error('Error reading %s: %s', path, e)
        sys.exit(1)

KB = 1024
MB_TO_GB = 1024
DEFAULT_INTERVAL_MS = 200
CLEAR_CMD = shutil.which('clear')

PMT_GUID_MTL = '0x130670b2'   # Meteor Lake telemetry GUID
PMT_GUID_ARL = '0x1306a0b3'   # Arrow Lake telemetry GUID
PMT_GUID_ARL_H = '0x1306a0b2' # Arrow Lake-H telemetry GUID
PMT_GUID_ARL_S = '0x1306a0b4' # Arrow Lake-S telemetry GUID
PMT_GUID_LNL = '0x3072005'    # Lunar Lake telemetry GUID
PMT_GUID_PTL = '0x3086000'    # Panther Lake telemetry GUID

def get_mtl_regs():
    return {
        'VPU_ENERGY': 0x628,
        'SOC_TEMPERATURES': 0x98,
        'VPU_WORKPOINT': 0x68,
        'VPU_MEMORY_BW': 0x0,
    }

def get_arl_regs():
    return get_mtl_regs()

def get_lnl_regs():
    return {
        'VPU_ENERGY': 0x5d0,
        'SOC_TEMPERATURES': 0x70,
        'VPU_WORKPOINT': 0x18,
        'VPU_MEMORY_BW': 0xc18
    }

def get_ptl_regs():
    return {
        'VPU_ENERGY': 0x670,
        'SOC_TEMPERATURES': 0x78,
        'VPU_WORKPOINT': 0x18,
        'VPU_MEMORY_BW': 0xc18
    }

class CpuGen(enum.IntEnum):
    MTL = 0
    ARL = 1
    LNL = 2
    PTL = 3

    def __str__(self):
        if self == CpuGen.MTL:
            return "Meteor Lake"
        if self == CpuGen.ARL:
            return "Arrow Lake"
        if self == CpuGen.LNL:
            return "Lunar Lake"
        if self == CpuGen.PTL:
            return "Panther Lake"
        return ""

def run_command(command: str, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    """Execute a shell command safely without shell=True."""
    try:
        cmd_list = shlex.split(command)
        return subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, # nosec B603: trusted command list, no shell
                     timeout=timeout, check=True, encoding='ascii', errors='ignore')
    except subprocess.TimeoutExpired as err:
        return subprocess.CompletedProcess(command, 1, err.stdout or '')
    except subprocess.CalledProcessError as err:
        return subprocess.CompletedProcess(command, err.returncode, err.stdout or '')
    except FileNotFoundError:
        return subprocess.CompletedProcess(command, 127, 'Executable not found')
    except OSError as err:
        return subprocess.CompletedProcess(command, 1, f'Execution failed: {err}')

class PmtTelemetry:
    """Handler for Intel PMT (Platform Monitoring Technology) telemetry data."""

    def __init__(self):
        self.pmt_root = '/sys/class/intel_pmt'
        self.buffer: Optional[bytes] = None
        self.regs: Optional[dict] = None
        self.telemetry_path: Optional[str] = None
        self.cpu_gen: Optional[CpuGen] = None

        # Check if PMT sysfs exists
        if not os.path.exists(self.pmt_root):
            LOG.error('PMT sysfs interface not found at %s', self.pmt_root)
            sys.exit(1)

        for telem_dir in os.listdir(self.pmt_root):
            if not telem_dir.startswith('telem'):
                continue

            telem_path = os.path.join(self.pmt_root, telem_dir)
            guid_path = os.path.join(telem_path, 'guid')
            telemetry_path = os.path.join(telem_path, 'telem')
            size_path = os.path.join(telem_path, 'size')
            offset_path = os.path.join(telem_path, 'offset')

            if not all(os.path.exists(p) for p in [guid_path, telemetry_path, size_path, offset_path]):
                continue

            guid = fdump(guid_path)
            telem_size = int(fdump(size_path))
            telem_offset = int(fdump(offset_path))

            LOG.debug('Found PMT device %s with GUID %s, size %d, offset %d',
                     telem_dir, guid, telem_size, telem_offset)

            self.telemetry_path = telemetry_path
            if guid == PMT_GUID_MTL:
                self.cpu_gen = CpuGen.MTL
                self.regs = get_mtl_regs()
                break
            if guid in (PMT_GUID_ARL, PMT_GUID_ARL_H, PMT_GUID_ARL_S):
                self.cpu_gen = CpuGen.ARL
                self.regs = get_arl_regs()
                break
            if guid == PMT_GUID_LNL:
                self.cpu_gen = CpuGen.LNL
                self.regs = get_lnl_regs()
                break
            if guid == PMT_GUID_PTL:
                self.cpu_gen = CpuGen.PTL
                self.regs = get_ptl_regs()
                break

        if self.cpu_gen is None:
            LOG.error('No CPU telemetry devices found with known GUIDs')
            sys.exit(1)

        LOG.debug('CPU generation detected: %s', self.cpu_gen)

    def read(self, offset, msb, lsb):
        """Function get_telem_sample slices bits from buffer buf at the container offset
        and bit masking specified by sample_spec."""
        buf = self.buffer
        if buf is None:
            LOG.error('Telemetry buffer is empty; ensure update_buffer() succeeded before read().')
            sys.exit(1)
        # read 8 bytes from buffer from offset and convert it to 64 bit little endian integer
        data = int.from_bytes(buf[offset:offset + 8],
                              byteorder='little')
        # create mask
        msb_mask = 0xffffffffffffffff & ((2 ** (int(msb) + 1)) - 1)
        lsb_mask = 0xffffffffffffffff & ((2 ** (int(lsb))) - 1)
        mask = msb_mask & (~lsb_mask)
        # apply mask and shift right
        value = (data & mask) >> int(lsb)
        return value

    def update_buffer(self) -> None:
        """Read telemetry data from sysfs into buffer."""
        try:
            with open(self.telemetry_path, 'rb') as fd:
                self.buffer = fd.read()
        except (FileNotFoundError, PermissionError, OSError) as e:
            LOG.error('Failed to read telemetry data: %s', e)
            sys.exit(1)

    def get_freq(self) -> float:
        """Get VPU frequency in MHz."""
        raw = self.read(self.regs['VPU_WORKPOINT'], 7, 0)
        if self.cpu_gen == CpuGen.MTL:
            return 2 * raw / 3 / 10
        return 0.05 * raw

    def get_display_freq_hz(self) -> float:
        """Get display frequency in Hz (converts MHz to Hz with hardware-specific scaling)."""
        freq_mhz = self.get_freq()
        return (freq_mhz * 1000) / 2

    def get_voltage(self) -> int:
        """Get VPU voltage reading."""
        return self.read(self.regs['VPU_WORKPOINT'], 15, 8)

    def get_tile_config(self) -> int:
        """Get NPU tile configuration."""
        return self.read(self.regs['VPU_WORKPOINT'], 23, 16)

    def get_npu_temperature(self) -> int:
        """Get NPU temperature in Celsius."""
        return self.read(self.regs['SOC_TEMPERATURES'], 47, 40)

    def get_npu_energy(self) -> float:
        """Get NPU energy consumption in joules (U32.18.14 fixed-point format)."""
        val = self.read(self.regs['VPU_ENERGY'], 63, 0)
        int_part = val >> 14
        float_part = (val & ((1 << 14) - 1)) / (1 << 14)
        return int_part + float_part

    def get_noc_bandwidth(self) -> float:
        """Get NoC (Network on Chip) bandwidth in MB/s."""
        val = self.read(self.regs['VPU_MEMORY_BW'], 31, 0)
        return val / 1e3

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

    # get ID based on 0000 prefix from /sys/bus/pci/drivers/intel_vpu/
    dev_path = "/sys/bus/pci/drivers/intel_vpu/"
    debugfs = "/sys/kernel/debug/accel/"
    pu = PmtTelemetry()
    if not os.path.exists(dev_path):
        print("Intel NPU driver 'intel_vpu' seems not to be loaded.\n")
        parser.print_help()
        sys.exit(1)

    for entry in os.listdir(dev_path):
        if entry.startswith("0000:"):
            dev_path = os.path.join(dev_path, entry)
            debugfs = os.path.join(debugfs, entry)
            break

    npu_busy = None
    if os.path.exists(os.path.join(dev_path, "npu_busy_time_us")):
        npu_busy = os.path.join(dev_path, "npu_busy_time_us")

    def read_busy_time():
        if npu_busy is None:
            return None
        try:
            return int(fdump(npu_busy))
        except (ValueError, RuntimeError) as err:
            LOG.warning('Failed to read busy time: %s', err)
            return None

    try:
        pciid = fdump(os.path.join(dev_path, "device"))
        fw_version = fdump(os.path.join(debugfs, "fw_version"))
    except RuntimeError as err:
        LOG.error('Failed to read device metadata: %s', err)
        sys.exit(1)

    ver_str = run_command('modinfo -F version intel_vpu').stdout.strip()
    driver_version = ver_str.split()[0] if ver_str else 'unknown'

    pu.update_buffer()
    prev_busy_time = read_busy_time()
    prev_energy = pu.get_npu_energy()
    interval = args.interval if args.interval else DEFAULT_INTERVAL_MS
    prev_bandwidth = pu.get_noc_bandwidth()

    # Memory utilization sysfs isn't exposed on N-1 platforms (e.g., MTL/ARL).
    # Only PTL and later platforms should attempt to read it.
    mem_util_supported = (pu.cpu_gen is not None) and (pu.cpu_gen >= CpuGen.PTL)
    mem_util_path = os.path.join(dev_path, "npu_memory_utilization")

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
            curr_busy_time = read_busy_time()
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

            mem_util_mb = -1.0
            mem_util_str = f'{"N/A":>31} [--]'
            if mem_util_supported:
                if os.path.exists(mem_util_path):
                    mem_util_raw = fdump(mem_util_path)
                    # from bytes to MB
                    try:
                        mem_util_mb = float(int(mem_util_raw)) / KB / KB
                    except (TypeError, ValueError) as err:
                        LOG.warning('Failed to parse memory utilization: %s', err)
                        mem_util_mb = -1.0

                    if mem_util_mb >= 0:
                        if mem_util_mb > MB_TO_GB:
                            mem_util = mem_util_mb / MB_TO_GB
                            mem_util_unit = 'GB'
                        else:
                            mem_util = mem_util_mb
                            mem_util_unit = 'MB'
                        mem_util_str = f'{mem_util:>31.2f} [{mem_util_unit}]'
                else:
                    LOG.debug('Memory utilization sysfs node not found at %s', mem_util_path)

            pu.update_buffer()

            curr_energy = pu.get_npu_energy()
            power = (curr_energy - prev_energy) / (interval * 1e-3)
            prev_energy = curr_energy
            freq_mhz = pu.get_freq()
            freq_hz = pu.get_display_freq_hz()
            tile_config = pu.get_tile_config()

            temp = pu.get_npu_temperature()

            curr_bandwidth = pu.get_noc_bandwidth()
            bandwidth_delta = curr_bandwidth - prev_bandwidth
            if curr_bandwidth > MB_TO_GB:
                bandwidth = bandwidth_delta / MB_TO_GB
                bw_unit = 'GB/s'
            else:
                bandwidth = bandwidth_delta
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

            if not args.interval:
                break
    finally:
        if csv_file:
            csv_file.close()


if __name__ == '__main__':
    main()
