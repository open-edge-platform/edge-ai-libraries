# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
CPU core type discovery (P, E, LPE) for Intel hybrid processors.

Reads Linux sysfs, which every container can see read-only, and classifies each
online logical CPU. The resolution order is:

1. Hybrid PMU lists in ``/sys/bus/event_source/devices``: ``cpu_core`` (P),
   ``cpu_atom`` (E) and ``cpu_lowpower`` (LPE). Atom CPUs without an L3 cache
   are LPE, which covers kernels that predate the ``cpu_lowpower`` PMU.
2. Cache shape, for CPUs no PMU list covers: no L3 means LPE, an L2 shared with
   CPUs that are not SMT siblings means E, anything else is P.
3. Non-hybrid CPUs are reported as UNIFORM instead of guessing P or E.

The method matches ``utils/obtain_cores.sh`` from
open-edge-platform/edge-workloads-and-benchmarks and the LPE rule in
OpenVINO's ``lin_system_conf.cpp``. The kernel attribute
``/sys/devices/system/cpu/cpuN/topology/core_type`` does not exist in
mainline Linux, so it is not used.

TODO(ITEP-97436): temporary. Replace the sysfs reader with the per-CPU core
types from the metrics-manager capabilities API once it provides them, and
keep ``get_cpu_topology()`` and ``CpuTopology`` unchanged for callers.
"""

import functools
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger("cpu_topology")

SYSFS_ROOT = Path("/sys")

_CPU_DIR = Path("devices/system/cpu")
_PMU_DIR = Path("bus/event_source/devices")


class CoreType(Enum):
    """Type of a logical CPU on an Intel processor."""

    P = "P"
    E = "E"
    LPE = "LPE"
    UNIFORM = "UNIFORM"


class TopologySource(Enum):
    """Where the core types in a CpuTopology came from."""

    SYSFS_PMU = "sysfs_pmu"
    SYSFS_CACHE = "sysfs_cache"
    UNIFORM = "uniform"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LogicalCpu:
    """
    One online logical CPU.

    Attributes:
        cpu (int): Logical CPU id, as used by taskset and DLSPS cpu_cores.
        core_type (CoreType): Classified type of the CPU.
        core_id (int): Lowest logical CPU id among its SMT siblings, so that
            hyper-threads of one physical core share the same value.
    """

    cpu: int
    core_type: CoreType
    core_id: int


@dataclass(frozen=True)
class CpuTopology:
    """
    Core types of all online logical CPUs.

    Attributes:
        cpus (tuple[LogicalCpu, ...]): Online CPUs sorted by id. Empty when
            the topology could not be read.
        source (TopologySource): Method that produced the classification.
    """

    cpus: tuple[LogicalCpu, ...]
    source: TopologySource

    @property
    def is_hybrid(self) -> bool:
        """True when the CPUs were classified into P, E or LPE types."""
        return any(c.core_type is not CoreType.UNIFORM for c in self.cpus)

    def cpus_of(self, core_type: CoreType) -> list[int]:
        """
        Return the logical CPU ids of the given type.

        Args:
            core_type (CoreType): Type to select.

        Returns:
            list[int]: Sorted logical CPU ids, empty if there are none.
        """
        return [c.cpu for c in self.cpus if c.core_type is core_type]

    def summary(self) -> str:
        """
        Return a one-line description for logs.

        Returns:
            str: For example "sysfs_pmu: P=0-5 E=6-13 LPE=14-15".
        """
        parts = [
            f"{core_type.value}={format_cpulist(cpus)}"
            for core_type in CoreType
            if (cpus := self.cpus_of(core_type))
        ]
        return f"{self.source.value}: {' '.join(parts) or 'no CPUs'}"


def parse_cpulist(text: str) -> set[int]:
    """
    Parse a kernel cpulist string such as "0-5,8,10-11".

    Args:
        text (str): Cpulist as printed by sysfs. Whitespace is ignored and an
            empty string means no CPUs.

    Returns:
        set[int]: Logical CPU ids in the list.

    Raises:
        ValueError: If the text is not a valid cpulist.
    """
    cpus: set[int] = set()
    text = text.strip()
    if not text:
        return cpus
    for part in text.split(","):
        first, sep, last = part.partition("-")
        start = int(first)
        end = int(last) if sep else start
        if start < 0 or end < start:
            raise ValueError(f"invalid cpulist range: {part!r}")
        cpus.update(range(start, end + 1))
    return cpus


def format_cpulist(cpus: Iterable[int]) -> str:
    """
    Format logical CPU ids as a compact kernel cpulist string.

    Args:
        cpus (Iterable[int]): Logical CPU ids in any order.

    Returns:
        str: For example "0-5,8,10-11", or an empty string for no CPUs.
    """
    ranges: list[str] = []
    ordered = sorted(set(cpus))
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[j] + 1:
            j += 1
        start, end = ordered[i], ordered[j]
        ranges.append(str(start) if start == end else f"{start}-{end}")
        i = j + 1
    return ",".join(ranges)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _read_cpulist(path: Path) -> set[int] | None:
    """Read a cpulist file; None when it is missing or malformed."""
    text = _read_text(path)
    if text is None:
        return None
    try:
        return parse_cpulist(text)
    except ValueError:
        logger.warning("Ignoring malformed cpulist in %s: %r", path, text)
        return None


def _thread_siblings(cpu_dir: Path, cpu: int) -> set[int]:
    siblings = _read_cpulist(cpu_dir / f"cpu{cpu}/topology/thread_siblings_list")
    return siblings or {cpu}


def _shared_caches(cpu_dir: Path, cpu: int) -> dict[int, set[int]]:
    """Map cache level to the CPUs sharing it, for data/unified caches."""
    levels: dict[int, set[int]] = {}
    for index_dir in sorted((cpu_dir / f"cpu{cpu}/cache").glob("index*")):
        level = _read_text(index_dir / "level")
        cache_type = _read_text(index_dir / "type")
        shared = _read_cpulist(index_dir / "shared_cpu_list")
        if level is None or not level.isdigit() or shared is None:
            continue
        if cache_type == "Instruction":
            continue
        levels[int(level)] = shared
    return levels


def _classify_by_cache(cpu_dir: Path, cpu: int) -> CoreType | None:
    """
    Classify a CPU from its cache shape.

    Returns:
        CoreType | None: LPE without L3, E when the L2 is shared with CPUs
            that are not SMT siblings, otherwise P. None when the L2 cannot be
            read, because then the shape says nothing.
    """
    levels = _shared_caches(cpu_dir, cpu)
    if 2 not in levels:
        return None
    if 3 not in levels:
        return CoreType.LPE
    if levels[2] - _thread_siblings(cpu_dir, cpu):
        return CoreType.E
    return CoreType.P


def _build(
    cpu_dir: Path, types: dict[int, CoreType], source: TopologySource
) -> CpuTopology:
    cpus = tuple(
        LogicalCpu(
            cpu=cpu,
            core_type=core_type,
            core_id=min(_thread_siblings(cpu_dir, cpu)),
        )
        for cpu, core_type in sorted(types.items())
    )
    return CpuTopology(cpus=cpus, source=source)


def read_cpu_topology(sysfs_root: Path = SYSFS_ROOT) -> CpuTopology:
    """
    Read and classify the core types of all online CPUs from sysfs.

    Args:
        sysfs_root (Path, optional): Root of the sysfs tree. Tests point it at
            a fake tree. Defaults to /sys.

    Returns:
        CpuTopology: Classified CPUs. Source UNAVAILABLE with no CPUs when the
            online CPU list cannot be read or no method applies.
    """
    cpu_dir = sysfs_root / _CPU_DIR
    pmu_dir = sysfs_root / _PMU_DIR

    online = _read_cpulist(cpu_dir / "online")
    if not online:
        return CpuTopology(cpus=(), source=TopologySource.UNAVAILABLE)

    core = _read_cpulist(pmu_dir / "cpu_core/cpus")
    atom = _read_cpulist(pmu_dir / "cpu_atom/cpus")
    lowpower = _read_cpulist(pmu_dir / "cpu_lowpower/cpus") or set()

    if core is not None or atom is not None:
        types: dict[int, CoreType] = {}
        for cpu in sorted(online):
            core_type: CoreType | None
            if cpu in lowpower:
                core_type = CoreType.LPE
            elif core is not None and cpu in core:
                core_type = CoreType.P
            elif atom is not None and cpu in atom:
                is_lpe = _classify_by_cache(cpu_dir, cpu) is CoreType.LPE
                core_type = CoreType.LPE if is_lpe else CoreType.E
            else:
                core_type = _classify_by_cache(cpu_dir, cpu)
            if core_type is None:
                logger.warning("Cannot classify CPU %d; leaving it out", cpu)
                continue
            types[cpu] = core_type
        return _build(cpu_dir, types, TopologySource.SYSFS_PMU)

    by_cache = {cpu: _classify_by_cache(cpu_dir, cpu) for cpu in sorted(online)}
    classified = {cpu: t for cpu, t in by_cache.items() if t is not None}
    if len(set(classified.values())) > 1:
        for cpu in sorted(online - classified.keys()):
            logger.warning("Cannot classify CPU %d; leaving it out", cpu)
        return _build(cpu_dir, classified, TopologySource.SYSFS_CACHE)

    if classified or (pmu_dir / "cpu").is_dir():
        uniform = dict.fromkeys(online, CoreType.UNIFORM)
        return _build(cpu_dir, uniform, TopologySource.UNIFORM)

    return CpuTopology(cpus=(), source=TopologySource.UNAVAILABLE)


@functools.cache
def get_cpu_topology() -> CpuTopology:
    """
    Return the CPU topology of this host, read once and cached.

    Never raises: any unexpected error is logged and reported as an
    UNAVAILABLE topology.

    Returns:
        CpuTopology: Classified online CPUs.
    """
    try:
        topology = read_cpu_topology()
    except Exception:
        logger.exception("Failed to read CPU topology from sysfs")
        return CpuTopology(cpus=(), source=TopologySource.UNAVAILABLE)

    if topology.source is TopologySource.UNAVAILABLE:
        logger.warning("CPU topology unavailable: cannot read it from sysfs")
    else:
        logger.info("CPU topology (%s)", topology.summary())
    return topology
