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
