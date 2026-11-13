from __future__ import annotations

from mcp_service_sdk import JSONLFileLog, SQLiteLog
from mcp_service_sdk.envelope import EventEnvelope


def _event(ref_id: str, event_type: str, ts_ms: int) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        service="test",
        store_id="store_001",
        payload={"ref_id": ref_id},
        ref_id=ref_id,
        ts_ms=ts_ms,
    )


def test_sqlite_read_filters_inclusive_time_range_and_preserves_order():
    log = SQLiteLog(service="test")
    log.append(_event("before", "activity", 99))
    log.append(_event("start", "activity", 100))
    log.append(_event("other-type", "other", 150))
    log.append(_event("end", "activity", 200))
    log.append(_event("after", "activity", 201))

    result = log.read(event_type="activity", start_ms=100, end_ms=200)

    assert [event.ref_id for event in result] == ["start", "end"]


def test_sqlite_read_can_return_latest_rows_first():
    log = SQLiteLog(service="test")
    for timestamp in range(5):
        log.append(_event(f"event-{timestamp}", "activity", timestamp))

    result = log.read(event_type="activity", limit=2, newest_first=True)

    assert [event.ref_id for event in result] == ["event-4", "event-3"]


def test_service_emit_uses_explicit_event_timestamp():
    from mcp_service_sdk import ServiceServer

    service = ServiceServer(service="test", store_id="store_001")

    event = service.emit("activity", {"value": 1}, ref_id="event-1", ts_ms=1234)

    assert event.ts_ms == 1234


def test_jsonl_read_filters_inclusive_time_range(tmp_path):
    log = JSONLFileLog(str(tmp_path / "events.jsonl"), service="test")
    log.append(_event("before", "activity", 99))
    log.append(_event("match", "activity", 100))
    log.append(_event("after", "activity", 201))

    result = log.read(event_type="activity", start_ms=100, end_ms=200)

    assert [event.ref_id for event in result] == ["match"]


def test_jsonl_read_can_return_latest_rows_first(tmp_path):
    log = JSONLFileLog(str(tmp_path / "events.jsonl"), service="test")
    for timestamp in range(5):
        log.append(_event(f"event-{timestamp}", "activity", timestamp))

    result = log.read(event_type="activity", limit=2, newest_first=True)

    assert [event.ref_id for event in result] == ["event-4", "event-3"]