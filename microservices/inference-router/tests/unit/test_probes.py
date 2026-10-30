# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for provider probes (spec, extract, aggregate, publish, runner)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.providers.base import ProviderMetadata
from src.providers.probes import ProbeHost, build_probes
from src.providers.probes.aggregator import MetricAggregator
from src.providers.probes.extract import FieldExtractor
from src.providers.probes.probe import ProviderProbe
from src.providers.probes.publish import MetadataSink, _set_metadata_path
from src.providers.probes.spec import ExtractRule, ProbeConfigError, ProbeSpec


# --------------------------------------------------------------------------- #
# Spec parsing
# --------------------------------------------------------------------------- #

def test_spec_defaults_applied():
    spec = ProbeSpec.from_mapping(
        {"name": "load", "extract": [{"regex": r"(\w+)\s+([0-9.]+)"}]}
    )
    assert spec.name == "load"
    assert spec.enabled is True
    assert spec.interval == 10.0
    assert spec.timeout == 5.0
    assert spec.method == "GET"
    assert spec.aggregate.window == 20
    assert spec.aggregate.method == "mean"
    # No publish declared → defaults to a metadata sink.
    assert [p.to for p in spec.publish] == ["metadata"]


def test_spec_both_expands_to_two_sinks():
    spec = ProbeSpec.from_mapping(
        {
            "name": "x",
            "extract": [{"regex": r"(\w+)\s+([0-9.]+)"}],
            "publish": [{"to": "both", "prefix": "attributes.probe", "path": "/tmp/x.jsonl"}],
        }
    )
    assert sorted(p.to for p in spec.publish) == ["file", "metadata"]


def test_spec_requires_extract():
    with pytest.raises(ProbeConfigError):
        ProbeSpec.from_mapping({"name": "x"})


def test_spec_file_sink_needs_path():
    with pytest.raises(ProbeConfigError):
        ProbeSpec.from_mapping(
            {"name": "x", "extract": [{"regex": "(a)(b)"}], "publish": [{"to": "file"}]}
        )


def test_extract_rule_requires_exactly_one_source():
    with pytest.raises(ProbeConfigError):
        ExtractRule(regex=r"x", json_path="a.b")
    with pytest.raises(ProbeConfigError):
        ExtractRule()


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

PROM_BODY = """
vllm:num_requests_running{model="Qwen"} 3.0
vllm:num_requests_waiting{model="Qwen"} 5.0
vllm:gpu_cache_usage_perc{model="Qwen"} 0.62
"""


def test_regex_extracts_many_named_series():
    rule = ExtractRule(regex=r"vllm:(\w*request\w*)\S*\s+([0-9.]+)")
    fields = FieldExtractor(rule).apply(PROM_BODY)
    # The gpu_cache line has no "request", so it is skipped.
    assert fields == {"num_requests_running": 3.0, "num_requests_waiting": 5.0}


def test_regex_skips_non_numeric_value():
    rule = ExtractRule(regex=r"(\w+)\s+(\S+)")
    fields = FieldExtractor(rule).apply("good 1.5\nbad notanumber")
    assert fields == {"good": 1.5}


def test_json_extract_names_by_last_segment():
    rule = ExtractRule(json_path="stats.pending")
    body = json.dumps({"stats": {"pending": 7}})
    assert FieldExtractor(rule).apply(body) == {"pending": 7.0}


def test_json_extract_missing_path_is_empty():
    rule = ExtractRule(json_path="stats.missing")
    assert FieldExtractor(rule).apply(json.dumps({"stats": {}})) == {}


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #

def test_aggregator_mean_over_window():
    agg = MetricAggregator(window=3, method="mean", max_series=10)
    for v in (1.0, 2.0, 3.0, 9.0):  # window=3 → keeps 2,3,9
        agg.add({"m": v})
    assert agg.values()["m"] == pytest.approx((2 + 3 + 9) / 3)


def test_aggregator_independent_series():
    agg = MetricAggregator(window=10, method="max", max_series=10)
    agg.add({"a": 1.0, "b": 5.0})
    agg.add({"a": 4.0, "b": 2.0})
    assert agg.values() == {"a": 4.0, "b": 5.0}


def test_aggregator_percentile():
    agg = MetricAggregator(window=100, method="p90", max_series=10)
    for v in range(1, 11):  # 1..10
        agg.add({"m": float(v)})
    # p90 over 1..10 (linear interp) = 9.1
    assert agg.values()["m"] == pytest.approx(9.1)


def test_aggregator_cardinality_cap():
    agg = MetricAggregator(window=5, method="mean", max_series=2)
    agg.add({"a": 1.0, "b": 2.0, "c": 3.0})  # c dropped by the cap
    assert set(agg.values()) == {"a", "b"}


def test_aggregator_latest_takes_most_recent_sample():
    agg = MetricAggregator(window=5, method="latest", max_series=10)
    for v in (1.0, 2.0, 7.0):
        agg.add({"m": v})
    assert agg.values()["m"] == 7.0


def test_aggregator_unknown_method_falls_back_to_mean():
    agg = MetricAggregator(window=5, method="bogus", max_series=10)
    assert agg.method == "mean"


# --------------------------------------------------------------------------- #
# Metadata sink / dotted-path writer
# --------------------------------------------------------------------------- #

def test_set_metadata_path_attributes():
    md = ProviderMetadata()
    _set_metadata_path(md, "attributes.probe.num_requests_running", 2.4)
    # attributes flatten to the top level in to_dict → read as probe.<name>.
    assert md.to_dict()["probe"]["num_requests_running"] == 2.4


def test_set_metadata_path_performance_field_promoted():
    md = ProviderMetadata()
    _set_metadata_path(md, "performance.ttft_ms", 123.0)
    assert isinstance(md.performance, dict)
    assert md.to_dict()["performance"]["ttft_ms"] == 123.0


def test_metadata_sink_normalizes_names():
    md = ProviderMetadata()

    class _Host:
        metadata = md

    class _Probe:
        host = _Host()

    MetadataSink("attributes.probe").emit(
        _Probe(), {'vllm:cache{model="Q"}': 0.6}
    )
    # Labels dropped, ':' replaced → vllm_cache
    assert md.to_dict()["probe"]["vllm_cache"] == 0.6


def test_file_sink_relative_path_resolves_against_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative file-sink path resolves under the workspace dir, not the CWD."""
    from src.providers.probes.publish import FileSink

    monkeypatch.setenv("GATEWAY_WORKSPACE", str(tmp_path))
    sink = FileSink("probes/local.perf.jsonl")
    assert sink.path == tmp_path / "probes" / "local.perf.jsonl"


def test_file_sink_absolute_path_used_verbatim(tmp_path: Path) -> None:
    """An absolute file-sink path is honored as-is (no workspace prefixing)."""
    from src.providers.probes.publish import FileSink

    absolute = tmp_path / "out.jsonl"
    assert FileSink(str(absolute)).path == absolute


def _emit_n(sink, n: int) -> None:
    """Drive ``n`` ticks through a sink with a stand-in probe."""
    class _Host:
        name = "local"

    class _Spec:
        name = "perf"

    class _Probe:
        host = _Host()
        spec = _Spec()

    for i in range(n):
        sink.emit(_Probe(), {"x": float(i)})


def test_file_sink_caps_entries_to_max(tmp_path: Path) -> None:
    """A long-running sink retains only the most recent ``max_entries`` records."""
    from src.providers.probes.publish import FileSink

    path = tmp_path / "hist.jsonl"
    sink = FileSink(str(path), max_entries=5)
    _emit_n(sink, 50)

    lines = path.read_text(encoding="utf-8").splitlines()
    # Bounded by max_entries + slack (slack = max(1, 5//10) = 1), never unbounded.
    assert len(lines) <= 6
    values = [json.loads(line)["aggregates"]["x"] for line in lines]
    # The retained tail is the newest records, in order.
    assert values[-1] == 49.0
    assert values == sorted(values)


def test_file_sink_max_entries_zero_is_unbounded(tmp_path: Path) -> None:
    """``max_entries=0`` disables the cap — every record is kept."""
    from src.providers.probes.publish import FileSink

    path = tmp_path / "hist.jsonl"
    sink = FileSink(str(path), max_entries=0)
    _emit_n(sink, 30)

    assert len(path.read_text(encoding="utf-8").splitlines()) == 30


def test_file_sink_cap_survives_restart(tmp_path: Path) -> None:
    """A fresh sink over an already-full file trims on the next overshoot.

    Simulates a process restart: the line count is re-seeded from disk so the
    history is not allowed to grow by another full ``max_entries`` first.
    """
    from src.providers.probes.publish import FileSink

    path = tmp_path / "hist.jsonl"
    _emit_n(FileSink(str(path), max_entries=5), 50)
    _emit_n(FileSink(str(path), max_entries=5), 10)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 6
    assert json.loads(lines[-1])["aggregates"]["x"] == 9.0


def test_file_sink_spec_parses_max_entries() -> None:
    """``max_entries`` flows from the publish spec into the built sink."""
    from src.providers.probes.publish import FileSink, build_sink
    from src.providers.probes.spec import DEFAULT_FILE_MAX_ENTRIES, ProbeSpec

    spec = ProbeSpec.from_mapping(
        {
            "name": "perf",
            "extract": [{"regex": r"(a)\s+(1)"}],
            "publish": [
                {"to": "file", "path": "a.jsonl", "max_entries": 3},
                {"to": "file", "path": "b.jsonl"},
            ],
        }
    )
    assert spec.publish[0].max_entries == 3
    assert spec.publish[1].max_entries == DEFAULT_FILE_MAX_ENTRIES
    assert isinstance(build_sink(spec.publish[0]), FileSink)
    assert build_sink(spec.publish[0]).max_entries == 3


@pytest.mark.parametrize("bad", [-1, "oops"])
def test_file_sink_rejects_invalid_max_entries(bad) -> None:
    from src.providers.probes.spec import ProbeConfigError, ProbeSpec

    with pytest.raises(ProbeConfigError):
        ProbeSpec.from_mapping(
            {
                "name": "perf",
                "extract": [{"regex": r"(a)\s+(1)"}],
                "publish": [{"to": "file", "path": "a.jsonl", "max_entries": bad}],
            }
        )


# --------------------------------------------------------------------------- #
# Runner (integration of the pipeline against fakes)
# --------------------------------------------------------------------------- #

class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeClient:
    """Stand-in httpx client: returns a canned body, or raises to force a fail."""

    def __init__(self, body: str | None):
        self.body = body
        self.calls = 0
        self.closed = False

    async def request(self, method, url, timeout=None):
        self.calls += 1
        if self.body is None:
            raise ConnectionError("boom")
        return _FakeResponse(self.body)

    async def aclose(self):
        self.closed = True


class _FakeHost(ProbeHost):
    def __init__(self, client, endpoint="http://x/metrics"):
        self.name = "fake"
        self.endpoint = endpoint
        self.metadata = ProviderMetadata()
        self._client = client
        self.probe_specs = []
        self._probes = {}

    async def probe_client(self):
        return self._client


def test_probe_tick_publishes_to_metadata_and_file(tmp_path: Path):
    file_path = tmp_path / "out.jsonl"
    spec = ProbeSpec.from_mapping(
        {
            "name": "load",
            "interval": 0.01,
            "extract": [{"regex": r"vllm:(num_requests_\w+)\S*\s+([0-9.]+)"}],
            "aggregate": {"window": 20, "method": "mean"},
            "publish": [
                {"to": "metadata", "prefix": "attributes.probe"},
                {"to": "file", "path": str(file_path)},
            ],
        }
    )
    host = _FakeHost(_FakeClient(PROM_BODY))
    probe = ProviderProbe(spec, host)

    # Drive one tick directly (deterministic, no sleeping loop).
    async def _drive():
        client = await host.probe_client()
        await probe._tick(client, host.endpoint)

    asyncio.run(_drive())

    md = host.metadata.to_dict()
    assert md["probe"]["num_requests_running"] == pytest.approx(3.0)
    assert md["probe"]["num_requests_waiting"] == pytest.approx(5.0)

    record = json.loads(file_path.read_text().strip())
    assert record["provider"] == "fake"
    assert record["probe"] == "load"
    assert record["aggregates"]["num_requests_running"] == pytest.approx(3.0)

    snap = probe.snapshot()
    assert snap["counters"] == {"success": 1, "fail": 0, "miss": 0}


def test_probe_tick_failure_increments_fail_counter():
    spec = ProbeSpec.from_mapping(
        {"name": "load", "extract": [{"regex": r"(\w+)\s+([0-9.]+)"}]}
    )
    host = _FakeHost(_FakeClient(None))
    probe = ProviderProbe(spec, host)

    async def _drive():
        client = await host.probe_client()
        await probe._tick(client, host.endpoint)

    asyncio.run(_drive())
    assert probe.snapshot()["counters"]["fail"] == 1


def test_start_and_stop_probes_lifecycle():
    spec_raw = {
        "name": "load",
        "enabled": True,
        "interval": 0.01,
        "extract": [{"regex": r"vllm:(num_requests_\w+)\S*\s+([0-9.]+)"}],
        "publish": [{"to": "metadata", "prefix": "attributes.probe"}],
    }
    client = _FakeClient(PROM_BODY)
    host = _FakeHost(client)
    host.probe_specs = [spec_raw]

    async def _drive():
        await host.start_probes()
        assert set(host.probe_snapshot()) == {"load"}
        assert host._probes["load"].running

        await asyncio.sleep(0.05)  # let a few ticks happen
        assert client.calls >= 1
        # Live metadata was updated by the running probe.
        assert "probe" in host.metadata.to_dict()

        host.stop_probes()
        await asyncio.sleep(0.02)  # allow the cancelled task to unwind

    asyncio.run(_drive())
    assert host._probes == {}
    assert client.closed is True


def test_disabled_probe_not_launched():
    host = _FakeHost(_FakeClient(PROM_BODY))
    host.probe_specs = [
        {
            "name": "off",
            "enabled": False,
            "extract": [{"regex": r"(\w+)\s+([0-9.]+)"}],
        }
    ]
    asyncio.run(host.start_probes())
    assert host.probe_snapshot() == {}


def test_build_probes_skips_invalid_spec():
    host = _FakeHost(_FakeClient(PROM_BODY))
    probes = build_probes(
        [
            {"name": "good", "extract": [{"regex": r"(\w+)\s+([0-9.]+)"}]},
            {"name": "bad"},  # missing extract → skipped, not fatal
        ],
        host=host,
    )
    assert [p.spec.name for p in probes] == ["good"]
