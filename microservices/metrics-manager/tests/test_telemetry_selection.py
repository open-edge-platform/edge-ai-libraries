# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Selection contracts; set TELEGRAF_TEST_BINARY to run real plugin fixtures."""

import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "native/packaging/etc"


def example(name):
    return (EXAMPLES / f"telegraf-{name}.conf.example").read_text()


def test_bundled_selection_contracts():
    for name, patterns in (
        ("network", ["eth*", "en*"]),
        ("network-virtual", ["veth*", "lxc*"]),
    ):
        inputs = tomllib.loads(example(name))["inputs"]
        assert inputs["net"][0]["interfaces"] == patterns
        assert inputs["ethtool"][0]["interface_include"] == patterns

    inputs = tomllib.loads(example("storage"))["inputs"]
    assert "mount_points" not in inputs["disk"][0]
    io = inputs["diskio"][0]
    assert io["devices"] == ["*"]
    assert io["device_tags"] == ["ID_MODEL"]
    assert io["skip_serial_number"] is True
    assert io["tagexclude"] == ["serial", "wwid"]
    assert io["tagdrop"] == {"name": ["loop*", "ram*"]}

    irq = tomllib.loads(example("interrupts"))["inputs"]["interrupts"][0]
    assert irq == {"cpu_as_tag": False, "tagpass": {"irq": ["[0-9]*"]}}


@pytest.fixture
def telegraf():
    binary = os.environ.get("TELEGRAF_TEST_BINARY")
    if not binary:
        pytest.skip("Set TELEGRAF_TEST_BINARY for real Telegraf selection tests")
    assert Path(binary).is_file(), "TELEGRAF_TEST_BINARY must point to an installed binary"
    return binary


def gather(binary, tmp_path, config):
    path = tmp_path / "telegraf.conf"
    path.write_text("[agent]\n  omit_hostname = true\n" + config)
    result = subprocess.run(
        [binary, "--config", str(path), "--test"],
        env={
            **os.environ,
            "HOST_PROC": str(tmp_path / "proc"),
            "HOST_SYS": str(tmp_path / "sys"),
            "HOST_DEV": str(tmp_path / "dev"),
            "HOST_RUN": str(tmp_path / "run"),
        },
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert "E!" not in result.stderr, result.stderr
    return [line.removeprefix("> ") for line in result.stdout.splitlines() if line.startswith("> ")]


def write_fixture(root, relative, text):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def net_config(name):
    return example(name).split("[[inputs.ethtool]]", 1)[0]


def test_real_network_primary_virtual_and_custom_selection(telegraf, tmp_path):
    names = ["eth0", "enp1s0", "veth-test", "lxc-test", "bond0", "wlan0", "br0", "lo"]
    lines = [
        "Inter-|   Receive                                                |  Transmit",
        " face |bytes packets errs drop fifo frame compressed multicast"
        " |bytes packets errs drop fifo colls carrier compressed",
    ]
    for name in names:
        lines.append(f"{name}: 1024 10 0 0 0 0 0 0 2048 20 0 0 0 0 0 0")
        write_fixture(tmp_path, f"sys/class/net/{name}/speed", "1000\n")
    write_fixture(tmp_path, "proc/net/dev", "\n".join(lines) + "\n")

    primary = net_config("network")
    virtual = net_config("network-virtual")
    for config, expected in (
        (primary, {"eth0", "enp1s0"}),
        (virtual, {"veth-test", "lxc-test"}),
        (primary + virtual, {"eth0", "enp1s0", "veth-test", "lxc-test"}),
        (primary.replace('["eth*", "en*"]', '["bond0", "wlan0"]'), {"bond0", "wlan0"}),
    ):
        metrics = gather(telegraf, tmp_path, config)
        assert {line.split(" ", 1)[0] for line in metrics} == {
            f"net,interface={name}" for name in expected
        }
        assert len(metrics) == len(expected)
        assert all("bytes_recv=1024u" in line and "bytes_sent=2048u" in line for line in metrics)


def test_real_diskio_selection_and_identifier_opt_in(telegraf, tmp_path):
    names = ["nvme0n1", "nvme0n1p1", "dm-0", "md0", "loop0", "ram0"]
    rows = []
    for minor, name in enumerate(names):
        rows.append(f"259 {minor} {name} 10 0 20 30 40 0 50 60 0 70 80")
        write_fixture(tmp_path, f"dev/{name}", "")
        write_fixture(tmp_path, f"sys/block/{name}/wwid", f"test-wwid-{name}\n")
    write_fixture(tmp_path, "proc/diskstats", "\n".join(rows) + "\n")
    # Regular fixture files have device number 0:0; no mknod or host disks needed.
    write_fixture(
        tmp_path,
        "run/udev/data/b0:0",
        "E:ID_MODEL=TestModel\nE:ID_SERIAL_SHORT=test-serial\n",
    )
    config = "[[inputs.diskio]]" + example("storage").split("[[inputs.diskio]]", 1)[1]
    private = gather(telegraf, tmp_path, config)
    assert len(private) == 4
    assert {line.split(" ", 1)[0] for line in private} == {
        f"diskio,ID_MODEL=TestModel,name={name}" for name in names[:4]
    }
    assert all("read_bytes=10240u" in line and "write_bytes=25600u" in line for line in private)
    assert not any("serial" in line.lower() or "wwid" in line for line in private)

    selected = gather(
        telegraf, tmp_path, config.replace('devices = ["*"]', 'devices = ["dm-0", "md0"]')
    )
    assert len(selected) == 2
    assert {line.split(" ", 1)[0] for line in selected} == {
        f"diskio,ID_MODEL=TestModel,name={name}" for name in ("dm-0", "md0")
    }

    opt_in = config.replace("skip_serial_number = true", "skip_serial_number = false")
    opt_in = opt_in.replace('tagexclude = ["serial", "wwid"]', "tagexclude = []")
    opt_in = opt_in.replace(
        'device_tags = ["ID_MODEL"]', 'device_tags = ["ID_MODEL", "ID_SERIAL_SHORT"]'
    )
    identified = gather(telegraf, tmp_path, opt_in)
    assert len(identified) == 4
    assert all("ID_SERIAL_SHORT=test-serial" in line and ",serial=" in line for line in identified)
    assert all(",wwid=test-wwid-" in line for line in identified)


def test_real_filesystem_mount_selection(telegraf, tmp_path):
    mounts, mountinfo = [], []
    for index, (name, fs) in enumerate((("app", "ext4"), ("other", "xfs"), ("volatile", "tmpfs"))):
        path = tmp_path / name
        path.mkdir()
        mounts.append(f"/dev/test{index} {path} {fs} rw 0 0")
        mountinfo.append(f"{index + 20} 1 259:{index} / {path} rw - {fs} /dev/test{index} rw")
    write_fixture(tmp_path, "proc/mounts", "\n".join(mounts) + "\n")
    for name in ("self", "1"):
        write_fixture(tmp_path, f"proc/{name}/mountinfo", "\n".join(mountinfo) + "\n")
    config = example("storage").split("[[inputs.diskio]]", 1)[0]
    metrics = gather(telegraf, tmp_path, config)
    assert len(metrics) == 2
    assert {line.split("path=", 1)[1].split(" ", 1)[0] for line in metrics} == {
        str(tmp_path / "app"),
        str(tmp_path / "other"),
    }
    selected = config.replace(
        '# mount_points = ["/", "/data"]',
        "mount_points = [" + json.dumps(str(tmp_path / "app")) + "]",
    )
    metrics = gather(telegraf, tmp_path, selected)
    assert len(metrics) == 1
    assert f"path={tmp_path / 'app'} " in metrics[0]


def test_real_irq_filter_retains_per_cpu_fields_and_allows_total_only(telegraf, tmp_path):
    fixture = write_fixture(
        tmp_path,
        "irq.lp",
        "interrupts,irq=16 total=3i,CPU0=1i,CPU1=2i\n"
        "interrupts,irq=17 total=7i,CPU0=3i,CPU1=4i\n"
        "interrupts,irq=NMI total=3i,CPU0=1i,CPU1=2i\n"
        "soft_interrupts,irq=TIMER total=3i,CPU0=1i,CPU1=2i\n",
    )
    # /proc/interrupts has no path override. Exercise the shipped common input
    # filter with deterministic line protocol rather than mounting over /proc.
    config = (
        '[[inputs.file]]\n data_format = "influx"\n files = ['
        + json.dumps(str(fixture))
        + "]\n"
        + example("interrupts")
        .split("[[inputs.interrupts]]", 1)[1]
        .replace("cpu_as_tag = false", "")
        .replace("[inputs.interrupts.tagpass]", "[inputs.file.tagpass]")
    )
    full = gather(telegraf, tmp_path, config)
    assert len(full) == 2
    assert {line.split(" ", 1)[0] for line in full} == {"interrupts,irq=16", "interrupts,irq=17"}
    assert all("CPU0=" in line and "CPU1=" in line and "total=" in line for line in full)
    total_only = config.replace(
        "[inputs.file.tagpass]", 'fieldinclude = ["total"]\n[inputs.file.tagpass]'
    )
    totals = gather(telegraf, tmp_path, total_only)
    assert len(totals) == 2
    assert all("CPU" not in line and "total=" in line for line in totals)
