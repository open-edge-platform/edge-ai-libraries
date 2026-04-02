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

import os
import sys
import enum
import logging as LOG
from pathlib import Path
from typing import Optional

from core.utils import fdump, run_command

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
        """Get NoC (Network on Chip) memory-traffic counter in MB.

        The PMT register reports a monotonically increasing counter (scaled in milli-MB), not an
        instantaneous rate. Convert to a bandwidth rate by taking a delta between two reads and
        dividing by elapsed time in seconds.
        """
        val = self.read(self.regs['VPU_MEMORY_BW'], 31, 0)
        return val / 1e3

class NpuMonitor:
    def __init__(self):
        # get ID based on 0000 prefix from /sys/bus/pci/drivers/intel_vpu/
        self.dev_path = "/sys/bus/pci/drivers/intel_vpu/"
        self.debugfs = "/sys/kernel/debug/accel/"
        self.npu_busy = None
        if self.core_setup() == True:
            self.pu = PmtTelemetry()
        else:
            self.pu = None

    def get_pmt_telemetry(self):
        return self.pu

    def core_setup(self) -> bool:
        if not os.path.exists(self.dev_path):
            LOG.error("Intel NPU driver 'intel_vpu' seems not to be loaded.\n")
            return False

        for entry in os.listdir(self.dev_path):
            if entry.startswith("0000:"):
                self.dev_path = os.path.join(self.dev_path, entry)
                self.debugfs = os.path.join(self.debugfs, entry)
                break

        if os.path.exists(os.path.join(self.dev_path, "npu_busy_time_us")):
            self.npu_busy_path = os.path.join(self.dev_path, "npu_busy_time_us")
        else:
            LOG.debug('"npu_busy_time_us" sysfs node not found at %s', self.dev_path)
            self.npu_busy_path = None

        if os.path.exists(os.path.join(self.dev_path, "npu_memory_utilization")):
            self.mem_util_path = os.path.join(self.dev_path, "npu_memory_utilization")
        else:
            LOG.debug('"npu_memory_utilization" sysfs node not found at %s', self.dev_path)
            self.mem_util_path = None

        if os.path.exists(os.path.join(self.dev_path, "device")):
            self.pciid_path = os.path.join(self.dev_path, "device")
        else:
            LOG.debug('"device" sysfs node not found at %s', self.dev_path)
            self.pciid_path = None

        if os.path.exists(os.path.join(self.debugfs, "fw_version")):
            self.fw_version_path = os.path.join(self.debugfs, "fw_version")
        else:
            LOG.debug('"fw_version" sysfs node not found at %s', self.debugfs)
            self.fw_version_path = None

        return True

    def read_fw_version(self) -> str:
        if self.fw_version_path is None:
            return None
        try:
            return fdump(self.fw_version_path)
        except (ValueError, RuntimeError) as err:
            LOG.warning('Failed to read NPU firmware version: %s', err)
            return None

    def read_driver_version(self) -> str:
        ver_str = run_command('modinfo -F version intel_vpu').stdout.strip()
        return ver_str.split()[0] if ver_str else 'unknown'

    def read_pciid(self) -> str:
        if self.pciid_path is None:
            return None
        try:
            return fdump(self.pciid_path)
        except (ValueError, RuntimeError) as err:
            LOG.warning('Failed to read PCI ID: %s', err)
            return None

    def read_busy_time(self) -> int:
        if self.npu_busy_path is None:
            return None
        try:
            return int(fdump(self.npu_busy_path))
        except (ValueError, RuntimeError) as err:
            LOG.warning('Failed to read busy time: %s', err)
            return None

    def read_mem_util(self) -> int:
        # We just return memory utilization as 0 if there is error in reading
        # sensible value
        if self.mem_util_path is None:
            return -1
        try:
            return int(fdump(self.mem_util_path))
        except (ValueError, RuntimeError) as err:
            LOG.warning('Failed to read mem util: %s', err)
            return -1
