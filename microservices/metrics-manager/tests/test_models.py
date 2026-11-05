# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for app/models.py."""

import pytest

from app.models import (
    InfluxLineProtocolInput,
    Metric,
    MetricsBatch,
    OpenTelemetryMetric,
    SimpleMetric,
)


class TestMetricTimestampNormalization:
    def test_seconds_converted_to_nanoseconds(self):
        m = Metric(name="x", fields={"v": 1}, timestamp=1704067200)
        assert m.timestamp == int(1704067200 * 1e9)

    def test_milliseconds_converted_to_nanoseconds(self):
        m = Metric(name="x", fields={"v": 1}, timestamp=1704067200000)
        assert m.timestamp == int(1704067200000 * 1e6)

    def test_nanoseconds_unchanged(self):
        ts_ns = int(1704067200 * 1e9)
        m = Metric(name="x", fields={"v": 1}, timestamp=ts_ns)
        assert m.timestamp == ts_ns

    def test_none_generates_current_timestamp(self):
        import time
        before = int(time.time() * 1e9)
        m = Metric(name="x", fields={"v": 1}, timestamp=None)
        after = int(time.time() * 1e9)
        assert before <= m.timestamp <= after

    def test_string_timestamp_parsed(self):
        m = Metric(name="x", fields={"v": 1}, timestamp="1704067200")
        assert m.timestamp == int(1704067200 * 1e9)


class TestMetricToInfluxLine:
    def test_simple_metric(self):
        m = Metric(name="cpu", fields={"usage": 45.2}, timestamp=int(1704067200 * 1e9))
        line = m.to_influx_line()
        assert line.startswith("cpu ")
        assert "usage=45.2" in line

    def test_bool_field_lowercase(self):
        m = Metric(name="ok", fields={"healthy": True})
        line = m.to_influx_line()
        assert "healthy=true" in line

    def test_int_field_has_i_suffix(self):
        m = Metric(name="counter", fields={"count": 42})
        line = m.to_influx_line()
        assert "count=42i" in line

    def test_str_field_quoted(self):
        m = Metric(name="event", fields={"msg": "hello"})
        line = m.to_influx_line()
        assert 'msg="hello"' in line

    def test_tags_sorted(self):
        m = Metric(name="cpu", fields={"v": 1.0}, tags={"z": "1", "a": "2"})
        line = m.to_influx_line()
        assert line.startswith("cpu,a=2,z=1 ")


class TestInfluxLineProtocolParsing:
    def test_valid_line_parsed(self):
        line = "cpu,host=server1 usage=45.2 1704067200000000000"
        metric = InfluxLineProtocolInput.parse_line(line)
        assert metric is not None
        assert metric.name == "cpu"
        assert metric.tags == {"host": "server1"}
        assert metric.fields["usage"] == 45.2

    def test_integer_field(self):
        metric = InfluxLineProtocolInput.parse_line("counter value=10i")
        assert metric.fields["value"] == 10

    def test_bool_field_true(self):
        metric = InfluxLineProtocolInput.parse_line("status healthy=true")
        assert metric.fields["healthy"] is True

    def test_bool_field_false(self):
        metric = InfluxLineProtocolInput.parse_line("status healthy=false")
        assert metric.fields["healthy"] is False

    def test_string_field_unquoted(self):
        metric = InfluxLineProtocolInput.parse_line('event msg="hello"')
        assert metric.fields["msg"] == "hello"

    def test_empty_line_returns_none(self):
        assert InfluxLineProtocolInput.parse_line("") is None
        assert InfluxLineProtocolInput.parse_line("   ") is None

    def test_malformed_line_returns_none(self):
        assert InfluxLineProtocolInput.parse_line("no_fields_here") is None

    def test_malformed_line_does_not_raise(self):
        # Should not raise; returns None gracefully
        result = InfluxLineProtocolInput.parse_line("bad \x00 line")
        # result can be None or a partial metric - either is fine
        assert result is None or hasattr(result, "name")


class TestOpenTelemetryMetricConversion:
    def _make_otlp(self, as_double=None, as_int=None):
        dp = {"timeUnixNano": str(int(1704067200 * 1e9))}
        if as_double is not None:
            dp["asDouble"] = as_double
        if as_int is not None:
            dp["asInt"] = as_int
        return {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "test_metric",
                                    "gauge": {"dataPoints": [dp]},
                                }
                            ]
                        }
                    ]
                }
            ]
        }

    def test_as_double_value_used_when_present(self):
        otlp = OpenTelemetryMetric(**self._make_otlp(as_double=99.5))
        metrics = otlp.to_metrics()
        assert len(metrics) == 1
        assert metrics[0].fields["value"] == 99.5

    def test_as_double_zero_not_replaced_by_as_int(self):
        """Regression: asDouble=0.0 must not fall through to asInt."""
        otlp = OpenTelemetryMetric(**self._make_otlp(as_double=0.0, as_int=999))
        metrics = otlp.to_metrics()
        assert metrics[0].fields["value"] == 0.0

    def test_as_int_used_when_no_as_double(self):
        otlp = OpenTelemetryMetric(**self._make_otlp(as_int=42))
        metrics = otlp.to_metrics()
        assert metrics[0].fields["value"] == 42

    def test_empty_resource_metrics_returns_empty(self):
        otlp = OpenTelemetryMetric(resourceMetrics=[])
        assert otlp.to_metrics() == []


class TestMetricsBatchValidation:
    def test_valid_batch_accepted(self):
        batch = MetricsBatch(metrics=[Metric(name="x", fields={"v": 1})])
        assert len(batch.metrics) == 1

    def test_empty_batch_rejected(self):
        with pytest.raises(Exception):
            MetricsBatch(metrics=[])

    def test_batch_exceeding_settings_limit_rejected(self):
        from unittest.mock import patch
        from app.settings import Settings

        small_limit = Settings(max_metrics_batch_size=2)
        metrics = [Metric(name="x", fields={"v": float(i)}) for i in range(3)]
        with patch("app.models.get_settings", return_value=small_limit):
            with pytest.raises(Exception, match="exceeds the configured limit"):
                MetricsBatch(metrics=metrics)


class TestSimpleMetricConversion:
    def test_to_metric_wraps_value(self):
        sm = SimpleMetric(name="fps", value=29.97)
        m = sm.to_metric()
        assert m.name == "fps"
        assert m.fields == {"value": 29.97}

    def test_tags_forwarded(self):
        sm = SimpleMetric(name="fps", value=1.0, tags={"cam": "1"})
        m = sm.to_metric()
        assert m.tags == {"cam": "1"}


class TestMetricBatchConversion:
    def test_to_influx_lines_single_metric(self):
        batch = MetricsBatch(metrics=[Metric(name="cpu", fields={"usage": 45.2})])
        lines = batch.to_influx_lines()
        assert "cpu" in lines
        assert "usage=45.2" in lines

    def test_to_influx_lines_multiple_metrics(self):
        batch = MetricsBatch(
            metrics=[
                Metric(name="cpu", fields={"usage": 45.2}),
                Metric(name="mem", fields={"percent": 70.0}),
            ]
        )
        lines = batch.to_influx_lines()
        assert "cpu" in lines
        assert "mem" in lines
        assert lines.count("\n") == 1

    def test_to_telegraf_json_preserves_fields(self):
        batch = MetricsBatch(metrics=[Metric(name="cpu", fields={"usage": 45.2})])
        result = batch.to_telegraf_json()
        assert len(result) == 1
        assert result[0]["name"] == "cpu"
        assert result[0]["fields"]["usage"] == 45.2


class TestTimestampNormalizationEdgeCases:
    def test_float_timestamp_converted_to_int(self):
        m = Metric(name="x", fields={"v": 1}, timestamp=1704067200.5)
        assert isinstance(m.timestamp, int)
        assert m.timestamp == int(1704067200 * 1e9)


class TestInfluxLineProtocolParsingEdgeCases:
    def test_escaped_comma_in_measurement(self):
        metric = InfluxLineProtocolInput.parse_line(r"cpu\,temp usage=45.2")
        assert metric.name == "cpu,temp"

    def test_escaped_space_in_tag_value(self):
        metric = InfluxLineProtocolInput.parse_line(r"cpu,host=server\ 1 usage=45.2")
        assert metric.tags["host"] == "server 1"

    def test_escaped_equals_in_tag_value(self):
        metric = InfluxLineProtocolInput.parse_line(r"cpu,key=val\=ue usage=45.2")
        assert metric.tags["key"] == "val=ue"

    def test_int_field_with_invalid_suffix(self):
        metric = InfluxLineProtocolInput.parse_line("counter value=10x")
        assert metric.fields["value"] == "10x"

    def test_int_field_with_non_numeric_value(self):
        metric = InfluxLineProtocolInput.parse_line("counter value=abci")
        if metric:
            assert isinstance(metric.fields, dict)

    def test_float_field_non_numeric_fallback(self):
        metric = InfluxLineProtocolInput.parse_line("test field=abc")
        assert metric.fields["field"] == "abc"

    def test_string_field_with_escaped_quotes(self):
        metric = InfluxLineProtocolInput.parse_line(r'event msg="hello\"world"')
        assert metric.fields["msg"] == 'hello"world'

    def test_string_field_with_escaped_backslash(self):
        metric = InfluxLineProtocolInput.parse_line(r'event msg="hello\\world"')
        assert metric.fields["msg"] == "hello\\world"

    def test_complex_escaped_string(self):
        metric = InfluxLineProtocolInput.parse_line(r'event msg="hello\\\"world"')
        assert metric.fields["msg"] == r'hello\"world'


class TestOpenTelemetryHistogram:
    def test_histogram_metric_type_is_accepted(self):
        payload = {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "request_latency",
                                    "histogram": {
                                        "dataPoints": [
                                            {"asDouble": 100.5, "timeUnixNano": "1704067200000000000"}
                                        ]
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        otlp = OpenTelemetryMetric(**payload)
        metrics = otlp.to_metrics()
        assert len(metrics) == 1
        assert metrics[0].fields["value"] == 100.5

    @staticmethod
    def _histogram_payload(dp: dict, resource_attrs: list | None = None) -> dict:
        return {
            "resourceMetrics": [
                {
                    "resource": {"attributes": resource_attrs or []},
                    "scopeMetrics": [
                        {"metrics": [{"name": "genai_ttft_ms", "histogram": {"dataPoints": [dp]}}]}
                    ],
                }
            ]
        }

    def test_histogram_point_becomes_count_sum_min_max_avg(self):
        dp = {
            "timeUnixNano": "1704067200000000000",
            "count": "4",
            "sum": 100.0,
            "min": 10.0,
            "max": 40.0,
            "bucketCounts": ["0", "4"],
            "explicitBounds": [5.0],
        }
        metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert len(metrics) == 1
        assert metrics[0].fields == {
            "count": 4,
            "sum": 100.0,
            "min": 10.0,
            "max": 40.0,
            "avg": 25.0,
        }
        assert metrics[0].metric_type == "histogram"

    def test_histogram_without_min_max_omits_them(self):
        dp = {"timeUnixNano": "1704067200000000000", "count": "2", "sum": 3.0}
        metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert metrics[0].fields == {"count": 2, "sum": 3.0, "avg": 1.5}

    def test_empty_histogram_has_no_avg(self):
        dp = {"timeUnixNano": "1704067200000000000", "count": "0", "sum": 0.0}
        metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert metrics[0].fields == {"count": 0, "sum": 0.0}

    def test_non_string_attributes_are_kept_as_text(self):
        dp = {
            "timeUnixNano": "1704067200000000000",
            "count": "1",
            "sum": 5.0,
            "attributes": [
                {"key": "pipeline_id", "value": {"stringValue": "abc"}},
                {"key": "stream", "value": {"intValue": "3"}},
                {"key": "ratio", "value": {"doubleValue": 0.5}},
                {"key": "warm", "value": {"boolValue": True}},
            ],
        }
        resource = [{"key": "service.name", "value": {"stringValue": "dlsps2"}}]
        metrics = OpenTelemetryMetric(**self._histogram_payload(dp, resource)).to_metrics()
        assert metrics[0].tags == {
            "service.name": "dlsps2",
            "pipeline_id": "abc",
            "stream": "3",
            "ratio": "0.5",
            "warm": "true",
        }

    def test_histogram_without_sum_has_no_sum_or_avg(self):
        dp = {"timeUnixNano": "1704067200000000000", "count": "3"}
        metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert metrics[0].fields == {"count": 3}

    def test_histogram_count_accepts_json_integer(self):
        dp = {"timeUnixNano": "1704067200000000000", "count": 2, "sum": 3.0}
        metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert metrics[0].fields["count"] == 2
        assert isinstance(metrics[0].fields["count"], int)

    def test_histogram_with_invalid_count_is_skipped(self, caplog):
        dp = {"timeUnixNano": "1704067200000000000", "count": "many", "sum": 3.0}
        with caplog.at_level("WARNING", logger="metrics-manager.models"):
            metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert metrics == []
        assert "Skipping malformed OTLP data point" in caplog.text

    def test_histogram_with_negative_count_is_skipped(self, caplog):
        dp = {"timeUnixNano": "1704067200000000000", "count": "-3", "sum": 3.0}
        with caplog.at_level("WARNING", logger="metrics-manager.models"):
            metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert metrics == []
        assert "Skipping malformed OTLP data point" in caplog.text

    @pytest.mark.parametrize(
        "non_finite",
        ["NaN", "Infinity", "-Infinity", "1e400", 10**400],
        ids=["nan", "inf", "-inf", "string-overflow", "int-overflow"],
    )
    def test_non_finite_histogram_values_are_dropped(self, non_finite):
        dp = {
            "timeUnixNano": "1704067200000000000",
            "count": "2",
            "sum": non_finite,
            "min": non_finite,
            "max": 2.0,
        }
        metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert metrics[0].fields == {"count": 2, "max": 2.0}
        assert metrics[0].to_influx_line() == "genai_ttft_ms count=2i,max=2.0 1704067200000000000"

    def test_histogram_fields_serialise_to_influx_line(self):
        dp = {"timeUnixNano": "1704067200000000000", "count": "2", "sum": 3.0}
        metrics = OpenTelemetryMetric(**self._histogram_payload(dp)).to_metrics()
        assert metrics[0].to_influx_line() == (
            "genai_ttft_ms count=2i,sum=3.0,avg=1.5 1704067200000000000"
        )


def _otlp_payload(metric: dict) -> dict:
    return {"resourceMetrics": [{"scopeMetrics": [{"metrics": [metric]}]}]}


class TestOpenTelemetryTemporality:
    _DP = {"timeUnixNano": "1704067200000000000", "count": "1", "sum": 2.0}

    @pytest.mark.parametrize(
        ("temporality", "expected"),
        [
            (1, "delta"),
            (2, "cumulative"),
            ("AGGREGATION_TEMPORALITY_DELTA", "delta"),
            ("AGGREGATION_TEMPORALITY_CUMULATIVE", "cumulative"),
        ],
    )
    def test_histogram_temporality_tag(self, temporality, expected):
        metric = {
            "name": "latency",
            "histogram": {"aggregationTemporality": temporality, "dataPoints": [self._DP]},
        }
        metrics = OpenTelemetryMetric(**_otlp_payload(metric)).to_metrics()
        assert metrics[0].tags["temporality"] == expected

    @pytest.mark.parametrize(
        ("temporality", "expected"),
        [(1, "delta"), ("AGGREGATION_TEMPORALITY_CUMULATIVE", "cumulative")],
    )
    def test_sum_temporality_tag(self, temporality, expected):
        metric = {
            "name": "frames_total",
            "sum": {
                "aggregationTemporality": temporality,
                "isMonotonic": True,
                "dataPoints": [{"asInt": "7", "timeUnixNano": "1704067200000000000"}],
            },
        }
        metrics = OpenTelemetryMetric(**_otlp_payload(metric)).to_metrics()
        assert metrics[0].tags["temporality"] == expected
        assert metrics[0].fields == {"value": 7}

    @pytest.mark.parametrize("temporality", [None, 0, "AGGREGATION_TEMPORALITY_UNSPECIFIED", 9])
    def test_unspecified_temporality_has_no_tag(self, temporality):
        histogram: dict = {"dataPoints": [self._DP]}
        if temporality is not None:
            histogram["aggregationTemporality"] = temporality
        metric = {"name": "latency", "histogram": histogram}
        metrics = OpenTelemetryMetric(**_otlp_payload(metric)).to_metrics()
        assert "temporality" not in metrics[0].tags

    def test_gauge_has_no_temporality_tag(self):
        metric = {
            "name": "fps",
            "gauge": {
                "aggregationTemporality": 1,
                "dataPoints": [{"asDouble": 30.0, "timeUnixNano": "1704067200000000000"}],
            },
        }
        metrics = OpenTelemetryMetric(**_otlp_payload(metric)).to_metrics()
        assert "temporality" not in metrics[0].tags


class TestOpenTelemetryAsInt:
    @staticmethod
    def _gauge(*values) -> dict:
        dps = [{"asInt": v, "timeUnixNano": "1704067200000000000"} for v in values]
        return _otlp_payload({"name": "frames", "gauge": {"dataPoints": dps}})

    def test_string_as_int_is_stored_as_integer(self):
        metrics = OpenTelemetryMetric(**self._gauge("42")).to_metrics()
        assert metrics[0].fields["value"] == 42
        assert isinstance(metrics[0].fields["value"], int)
        assert metrics[0].to_influx_line().startswith("frames value=42i ")

    def test_large_string_as_int_keeps_precision(self):
        metrics = OpenTelemetryMetric(**self._gauge("9007199254740993")).to_metrics()
        assert metrics[0].fields["value"] == 9007199254740993

    def test_invalid_as_int_point_is_skipped(self, caplog):
        with caplog.at_level("WARNING", logger="metrics-manager.models"):
            metrics = OpenTelemetryMetric(**self._gauge("abc", "5", 1.5)).to_metrics()
        assert [m.fields["value"] for m in metrics] == [5]
        assert caplog.text.count("Skipping malformed OTLP data point") == 2
