from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Query

from src.common.schema import TelemetryResponse
from src.common import settings
from src.core.telemetry.store import telemetry_store


telemetry_router = APIRouter(tags=["Telemetry"])

def _format_timestamp(value: Any) -> str:
	if isinstance(value, str):
		return value
	try:
		epoch = float(value)
		if epoch <= 0:
			epoch = 0.0
		return (
			datetime.fromtimestamp(epoch, tz=timezone.utc)
			.isoformat()
			.replace("+00:00", "Z")
		)
	except Exception:
		return str(value)


def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
	timestamps = record.get("timestamps")
	if isinstance(timestamps, dict):
		if "requested_at" in timestamps:
			timestamps["requested_at"] = _format_timestamp(timestamps["requested_at"])
		if "completed_at" in timestamps:
			timestamps["completed_at"] = _format_timestamp(timestamps["completed_at"])
	return record


@telemetry_router.get(
	"/telemetry",
	response_model=TelemetryResponse,
	response_model_exclude_none=True,
)
def read_telemetry(limit: int = Query(100, ge=1, le=settings.TELEMETRY_MAX_RECORDS)) -> TelemetryResponse:
	"""Return the most recent telemetry entries (newest first)."""

	entries = telemetry_store.read_latest(limit)
	normalized = [_normalize_record(dict(entry)) for entry in entries]
	return TelemetryResponse(count=len(normalized), items=normalized)
