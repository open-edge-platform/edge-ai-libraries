"""Telemetry record builder and persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from src.common import logger
from src.common.schema import (
	TelemetryBatchDetail,
	TelemetryCounts,
	TelemetryProcessingConfig,
	TelemetryRecord,
	TelemetryStageTiming,
	TelemetryThroughput,
	TelemetryTimestamps,
	TelemetryVideoMetadata,
)
from src.core.telemetry.store import telemetry_store


def _safe_div(numerator: float, denominator: float) -> float:
	return numerator / denominator if denominator > 0 else 0.0


def _format_timestamp(epoch_seconds: float) -> str:
	if epoch_seconds <= 0:
		return datetime.fromtimestamp(0, tz=timezone.utc).isoformat().replace("+00:00", "Z")
	return (
		datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
		.isoformat()
		.replace("+00:00", "Z")
	)


def _build_stage_timings(
	*,
	frame_extraction_seconds: float,
	detection_seconds: float,
	embedding_seconds: float,
	storage_seconds: float,
	total_wall_seconds: float,
) -> List[TelemetryStageTiming]:
	stages: List[tuple[str, float]] = [
		("extraction", frame_extraction_seconds),
		("detection", detection_seconds),
		("embedding", embedding_seconds),
		("storage", storage_seconds),
	]
	safe_wall = max(total_wall_seconds, 1e-9)

	extraction_seconds_safe = max(frame_extraction_seconds, 0.0)
	extraction_pct = min(_safe_div(extraction_seconds_safe, safe_wall) * 100.0, 100.0)

	parallel_budget_seconds = max(safe_wall - extraction_seconds_safe, 0.0)
	parallel_scale_pct = _safe_div(parallel_budget_seconds, safe_wall) * 100.0
	parallel_total = sum(
		max(seconds, 0.0)
		for name, seconds in stages
		if name != "extraction"
	)

	results: List[TelemetryStageTiming] = []
	for name, seconds in stages:
		pct: float
		if name == "extraction":
			pct = extraction_pct
		else:
			if parallel_total > 0 and parallel_scale_pct > 0:
				pct = min(
					_safe_div(max(seconds, 0.0), parallel_total) * parallel_scale_pct,
					100.0,
				)
			else:
				pct = 0.0
		results.append(
			TelemetryStageTiming(name=name, seconds=seconds, percent_of_total=pct)
		)
	return results


def _convert_batches(raw_batches: Iterable[Dict[str, Any]]) -> List[TelemetryBatchDetail]:
	details: List[TelemetryBatchDetail] = []
	for idx, batch in enumerate(raw_batches, start=1):
		details.append(
			TelemetryBatchDetail(
				batch_index=batch.get("batch_index", idx),
				input_frames=batch.get("input_frames", 0),
				items_after_detection=batch.get("items_after_detection", 0),
				detection_seconds=float(batch.get("detection_time", 0.0)),
				embedding_seconds=float(batch.get("embedding_time", 0.0)),
				storage_seconds=float(batch.get("storage_time", 0.0)),
				total_seconds=float(batch.get("processing_time", 0.0)),
				embeddings_stored=int(batch.get("embeddings_count", 0)),
			)
		)
	return details


def record_video_telemetry(
	*,
	context: Dict[str, Any],
	video_metadata: Dict[str, Any],
	pipeline_stats: Dict[str, Any],
	config: Dict[str, Any],
) -> Optional[TelemetryRecord]:
	"""Build, persist, and return a telemetry entry."""

	try:
		total_wall = float(pipeline_stats.get("total_wall_seconds", 0.0))
		extraction_seconds = float(pipeline_stats.get("frame_extraction_seconds", 0.0))
		detection_seconds = float(pipeline_stats.get("detection_seconds", 0.0))
		embedding_seconds = float(pipeline_stats.get("embedding_seconds_total", 0.0))
		storage_seconds = float(pipeline_stats.get("storage_seconds_total", 0.0))
		frame_count = int(pipeline_stats.get("frames_extracted", 0))
		items_after_detection = int(pipeline_stats.get("items_after_detection", 0))
		embeddings_stored = int(pipeline_stats.get("embeddings_stored", 0))

		stages = _build_stage_timings(
			frame_extraction_seconds=extraction_seconds,
			detection_seconds=detection_seconds,
			embedding_seconds=embedding_seconds,
			storage_seconds=storage_seconds,
			total_wall_seconds=total_wall,
		)

		batches = _convert_batches(pipeline_stats.get("batches", []))

		counts = TelemetryCounts(
			frames_extracted=frame_count,
			items_after_detection=items_after_detection,
			embeddings_stored=embeddings_stored,
		)

		embedding_stage_pct = next(
			(stage.percent_of_total for stage in stages if stage.name == "embedding"),
			0.0,
		)
		effective_embedding_seconds = total_wall * (embedding_stage_pct / 100.0)
		if effective_embedding_seconds <= 0:
			effective_embedding_seconds = total_wall

		throughput = TelemetryThroughput(
			embeddings_per_second=_safe_div(embeddings_stored, effective_embedding_seconds),
			embedding_stage_embeddings_per_second=_safe_div(
				embeddings_stored, embedding_seconds
			),
			wall_time_embeddings_per_second=_safe_div(embeddings_stored, total_wall),
			frames_per_second=_safe_div(
				frame_count,
				extraction_seconds if extraction_seconds > 0 else total_wall,
			),
		)

		timestamps = TelemetryTimestamps(
			requested_at=_format_timestamp(float(context.get("requested_at", 0.0))),
			completed_at=_format_timestamp(float(context.get("completed_at", 0.0))),
			wall_time_seconds=total_wall,
		)

		video = TelemetryVideoMetadata(
			bucket_name=video_metadata.get("bucket_name", ""),
			video_id=video_metadata.get("video_id", ""),
			filename=video_metadata.get("filename", ""),
			frame_interval=int(video_metadata.get("frame_interval", 0) or 0),
			fps=video_metadata.get("fps"),
			total_frames=video_metadata.get("total_frames"),
			video_duration_seconds=video_metadata.get("video_duration_seconds"),
			tags=list(video_metadata.get("tags", [])),
			video_url=video_metadata.get("video_url"),
			video_rel_url=video_metadata.get("video_rel_url"),
			processing_mode=video_metadata.get("processing_mode"),
		)

		processing_config = TelemetryProcessingConfig(
			embedding_mode=config.get("embedding_mode", "unknown"),
			object_detection_enabled=bool(config.get("object_detection_enabled", False)),
			detection_confidence=config.get("detection_confidence"),
			sdk_parallel_workers=config.get("sdk_parallel_workers"),
			sdk_batch_size=config.get("sdk_batch_size"),
		)

		record = TelemetryRecord(
			request_id=context.get("request_id", ""),
			source=context.get("source", ""),
			processing_mode=config.get("embedding_mode", "unknown"),
			timestamps=timestamps,
			video=video,
			config=processing_config,
			counts=counts,
			stages=stages,
			throughput=throughput,
			batches=batches,
		)

		telemetry_store.append(record.model_dump())
		return record
	except Exception as exc:  # pragma: no cover - telemetry must not break pipeline
		logger.warning("Failed to record telemetry: %s", exc)
		return None


__all__ = ["record_video_telemetry"]
