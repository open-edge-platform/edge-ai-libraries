# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cpu_topology
from cpu_topology import (
    CoreType,
    CpuTopology,
    LogicalCpu,
    TopologySource,
    format_cpulist,
    get_cpu_topology,
    parse_cpulist,
    read_cpu_topology,
)

P, E, LPE, UNIFORM = CoreType.P, CoreType.E, CoreType.LPE, CoreType.UNIFORM


class FakeSysfs:
    """Builds a minimal sysfs tree with the files cpu_topology reads."""

    def __init__(self, root: Path):
        self.root = root
        self.cpu_dir = root / "devices/system/cpu"
        self.pmu_dir = root / "bus/event_source/devices"
        self.cpu_dir.mkdir(parents=True)
        self.pmu_dir.mkdir(parents=True)

    def online(self, text: str) -> None:
        (self.cpu_dir / "online").write_text(text + "\n")

    def pmu(self, name: str, cpus: str | None = None) -> None:
        pmu = self.pmu_dir / name
        pmu.mkdir()
        if cpus is not None:
            (pmu / "cpus").write_text(cpus + "\n")

    def cpu(
        self,
        cpu: int,
        siblings: str,
        l2: str | None,
        l3: str | None,
    ) -> None:
        cpu_path = self.cpu_dir / f"cpu{cpu}"
        topology = cpu_path / "topology"
        topology.mkdir(parents=True)
        (topology / "thread_siblings_list").write_text(siblings + "\n")
        caches = [(1, "Data", siblings), (1, "Instruction", siblings)]
        if l2 is not None:
            caches.append((2, "Unified", l2))
        if l3 is not None:
            caches.append((3, "Unified", l3))
        for index, (level, cache_type, shared) in enumerate(caches):
            index_dir = cpu_path / f"cache/index{index}"
            index_dir.mkdir(parents=True)
            (index_dir / "level").write_text(f"{level}\n")
            (index_dir / "type").write_text(cache_type + "\n")
            (index_dir / "shared_cpu_list").write_text(shared + "\n")


def build_arl_h(sysfs: FakeSysfs, with_lowpower_pmu: bool = True) -> None:
    """Core Ultra 9 285H: 6 P (0-5), 8 E (6-13), 2 LPE (14-15), no SMT."""
    sysfs.online("0-15")
    sysfs.pmu("cpu_core", "0-5")
    sysfs.pmu("cpu_atom", "6-13")
    if with_lowpower_pmu:
        sysfs.pmu("cpu_lowpower", "14-15")
    for cpu in range(6):
        sysfs.cpu(cpu, str(cpu), l2=str(cpu), l3="0-13")
    for cpu in range(6, 14):
        cluster = "6-9" if cpu < 10 else "10-13"
        sysfs.cpu(cpu, str(cpu), l2=cluster, l3="0-13")
    for cpu in (14, 15):
        sysfs.cpu(cpu, str(cpu), l2="14-15", l3=None)


def build_mtl_h(sysfs: FakeSysfs) -> None:
    """
    Core Ultra 7 155H on a kernel without the cpu_lowpower PMU:
    6 P with SMT (0-11), 8 E (12-19), 2 LPE listed as atom (20-21).
    """
    sysfs.online("0-21")
    sysfs.pmu("cpu_core", "0-11")
    sysfs.pmu("cpu_atom", "12-21")
    for cpu in range(12):
        pair = f"{cpu - cpu % 2}-{cpu - cpu % 2 + 1}"
        sysfs.cpu(cpu, pair, l2=pair, l3="0-19")
    for cpu in range(12, 20):
        cluster = "12-15" if cpu < 16 else "16-19"
        sysfs.cpu(cpu, str(cpu), l2=cluster, l3="0-19")
    for cpu in (20, 21):
        sysfs.cpu(cpu, str(cpu), l2="20-21", l3=None)


class SysfsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sysfs = FakeSysfs(Path(self._tmp.name))

    def read(self) -> CpuTopology:
        return read_cpu_topology(self.sysfs.root)


class TestParseCpulist(unittest.TestCase):
    def test_parses_ranges_and_singles(self):
        self.assertEqual(parse_cpulist("0-2,5,8-9\n"), {0, 1, 2, 5, 8, 9})

    def test_empty_string_is_no_cpus(self):
        self.assertEqual(parse_cpulist(" \n"), set())

    def test_rejects_malformed_input(self):
        for text in ("a", "3-1", "-1", "1-", "1,,2"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_cpulist(text)


class TestFormatCpulist(unittest.TestCase):
    def test_compacts_consecutive_ids(self):
        self.assertEqual(format_cpulist([9, 0, 1, 2, 5, 8]), "0-2,5,8-9")

    def test_empty(self):
        self.assertEqual(format_cpulist([]), "")

    def test_round_trip(self):
        self.assertEqual(format_cpulist(parse_cpulist("0-5,7,9-13")), "0-5,7,9-13")


class TestHybridPmu(SysfsTestCase):
    def test_arl_h_matches_obtain_cores(self):
        """Same split as obtain_cores.sh prints on a 285H."""
        build_arl_h(self.sysfs)
        topology = self.read()
        self.assertEqual(topology.source, TopologySource.SYSFS_PMU)
        self.assertTrue(topology.is_hybrid)
        self.assertEqual(topology.cpus_of(P), list(range(0, 6)))
        self.assertEqual(topology.cpus_of(E), list(range(6, 14)))
        self.assertEqual(topology.cpus_of(LPE), [14, 15])
        self.assertEqual(topology.summary(), "sysfs_pmu: P=0-5 E=6-13 LPE=14-15")

    def test_lpe_missing_from_all_pmu_lists_uses_cache(self):
        """Older kernels list LPE CPUs in no PMU at all."""
        build_arl_h(self.sysfs, with_lowpower_pmu=False)
        topology = self.read()
        self.assertEqual(topology.source, TopologySource.SYSFS_PMU)
        self.assertEqual(topology.cpus_of(LPE), [14, 15])
        self.assertEqual(topology.cpus_of(E), list(range(6, 14)))

    def test_mtl_h_atom_without_l3_is_lpe_and_smt_shares_core_id(self):
        build_mtl_h(self.sysfs)
        topology = self.read()
        self.assertEqual(topology.cpus_of(P), list(range(0, 12)))
        self.assertEqual(topology.cpus_of(E), list(range(12, 20)))
        self.assertEqual(topology.cpus_of(LPE), [20, 21])
        by_cpu = {c.cpu: c for c in topology.cpus}
        self.assertEqual(by_cpu[0].core_id, 0)
        self.assertEqual(by_cpu[1].core_id, 0)
        self.assertEqual(by_cpu[11].core_id, 10)
        self.assertEqual(by_cpu[12].core_id, 12)

    def test_offline_cpus_are_left_out(self):
        build_arl_h(self.sysfs)
        self.sysfs.online("0-12,14")
        topology = self.read()
        self.assertEqual([c.cpu for c in topology.cpus], [*range(13), 14])
        self.assertEqual(topology.cpus_of(LPE), [14])

    def test_atom_cpu_with_unreadable_cache_stays_e(self):
        build_arl_h(self.sysfs)
        for index_dir in (self.sysfs.cpu_dir / "cpu6/cache").glob("index*"):
            (index_dir / "level").unlink()
        self.assertIn(6, self.read().cpus_of(E))

    def test_unclassifiable_cpu_is_left_out(self):
        build_arl_h(self.sysfs, with_lowpower_pmu=False)
        for index_dir in (self.sysfs.cpu_dir / "cpu15/cache").glob("index*"):
            (index_dir / "shared_cpu_list").unlink()
        with self.assertLogs("cpu_topology", level="WARNING"):
            topology = self.read()
        self.assertNotIn(15, [c.cpu for c in topology.cpus])
        self.assertEqual(topology.cpus_of(LPE), [14])

    def test_malformed_pmu_list_falls_back_to_cache(self):
        build_arl_h(self.sysfs)
        (self.sysfs.pmu_dir / "cpu_atom/cpus").write_text("garbage\n")
        with self.assertLogs("cpu_topology", level="WARNING"):
            topology = self.read()
        self.assertEqual(topology.source, TopologySource.SYSFS_PMU)
        self.assertEqual(topology.cpus_of(E), list(range(6, 14)))


class TestCacheFallback(SysfsTestCase):
    def _remove_hybrid_pmus(self):
        for name in ("cpu_core", "cpu_atom"):
            (self.sysfs.pmu_dir / name / "cpus").unlink()
            (self.sysfs.pmu_dir / name).rmdir()

    def test_hybrid_without_pmu_dirs(self):
        build_mtl_h(self.sysfs)
        self._remove_hybrid_pmus()
        topology = self.read()
        self.assertEqual(topology.source, TopologySource.SYSFS_CACHE)
        self.assertEqual(topology.cpus_of(P), list(range(0, 12)))
        self.assertEqual(topology.cpus_of(E), list(range(12, 20)))
        self.assertEqual(topology.cpus_of(LPE), [20, 21])

    def test_unclassifiable_cpu_is_left_out(self):
        build_mtl_h(self.sysfs)
        self._remove_hybrid_pmus()
        for index_dir in (self.sysfs.cpu_dir / "cpu13/cache").glob("index*"):
            (index_dir / "level").unlink()
        with self.assertLogs("cpu_topology", level="WARNING") as logs:
            topology = self.read()
        self.assertEqual(topology.source, TopologySource.SYSFS_CACHE)
        self.assertNotIn(13, [c.cpu for c in topology.cpus])
        self.assertIn("Cannot classify CPU 13", logs.output[0])


class TestUniform(SysfsTestCase):
    def test_xeon_with_smt_is_uniform(self):
        self.sysfs.online("0-7")
        self.sysfs.pmu("cpu")
        for cpu in range(8):
            pair = f"{cpu - cpu % 2}-{cpu - cpu % 2 + 1}"
            self.sysfs.cpu(cpu, pair, l2=pair, l3="0-7")
        topology = self.read()
        self.assertEqual(topology.source, TopologySource.UNIFORM)
        self.assertFalse(topology.is_hybrid)
        self.assertEqual(topology.cpus_of(UNIFORM), list(range(8)))
        self.assertEqual([c.core_id for c in topology.cpus], [0, 0, 2, 2, 4, 4, 6, 6])

    def test_e_core_only_part_is_uniform_not_e(self):
        """N-series: shared L2 like E-cores, but nothing to compare against."""
        self.sysfs.online("0-3")
        for cpu in range(4):
            self.sysfs.cpu(cpu, str(cpu), l2="0-3", l3="0-3")
        topology = self.read()
        self.assertEqual(topology.source, TopologySource.UNIFORM)
        self.assertEqual(topology.cpus_of(UNIFORM), [0, 1, 2, 3])

    def test_cpu_pmu_without_cache_info_is_uniform(self):
        self.sysfs.online("0-1")
        self.sysfs.pmu("cpu")
        topology = self.read()
        self.assertEqual(topology.source, TopologySource.UNIFORM)
        self.assertEqual([c.core_id for c in topology.cpus], [0, 1])


class TestUnavailable(SysfsTestCase):
    def test_missing_online_list(self):
        topology = self.read()
        self.assertEqual(topology, CpuTopology((), TopologySource.UNAVAILABLE))
        self.assertFalse(topology.is_hybrid)
        self.assertEqual(topology.summary(), "unavailable: no CPUs")

    def test_malformed_online_list(self):
        self.sysfs.online("x")
        with self.assertLogs("cpu_topology", level="WARNING"):
            topology = self.read()
        self.assertEqual(topology.source, TopologySource.UNAVAILABLE)

    def test_no_pmu_and_no_cache_info(self):
        self.sysfs.online("0-3")
        self.assertEqual(self.read().source, TopologySource.UNAVAILABLE)

    def test_nonexistent_root(self):
        topology = read_cpu_topology(Path(self._tmp.name) / "missing")
        self.assertEqual(topology.source, TopologySource.UNAVAILABLE)


class TestGetCpuTopology(unittest.TestCase):
    def setUp(self):
        get_cpu_topology.cache_clear()
        self.addCleanup(get_cpu_topology.cache_clear)

    def test_reads_once_and_logs_summary(self):
        topology = CpuTopology(
            cpus=(LogicalCpu(cpu=0, core_type=P, core_id=0),),
            source=TopologySource.SYSFS_PMU,
        )
        with patch.object(
            cpu_topology, "read_cpu_topology", return_value=topology
        ) as read:
            with self.assertLogs("cpu_topology", level="INFO") as logs:
                self.assertIs(get_cpu_topology(), topology)
            self.assertIs(get_cpu_topology(), topology)
        read.assert_called_once_with()
        self.assertIn("CPU topology (sysfs_pmu: P=0)", logs.output[0])

    def test_unexpected_error_returns_unavailable(self):
        with patch.object(
            cpu_topology, "read_cpu_topology", side_effect=RuntimeError("boom")
        ):
            with self.assertLogs("cpu_topology", level="ERROR"):
                topology = get_cpu_topology()
        self.assertEqual(topology.source, TopologySource.UNAVAILABLE)
        self.assertEqual(topology.cpus, ())

    def test_unavailable_is_logged_as_warning(self):
        unavailable = CpuTopology(cpus=(), source=TopologySource.UNAVAILABLE)
        with patch.object(cpu_topology, "read_cpu_topology", return_value=unavailable):
            with self.assertLogs("cpu_topology", level="WARNING") as logs:
                get_cpu_topology()
        self.assertIn("unavailable", logs.output[0])


if __name__ == "__main__":
    unittest.main()
