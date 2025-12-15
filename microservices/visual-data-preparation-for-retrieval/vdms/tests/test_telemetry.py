from src.core.telemetry.store import TelemetryStore


def test_telemetry_store_retains_latest(tmp_path):
	store_path = tmp_path / "telemetry.jsonl"
	store = TelemetryStore(store_path, max_records=3)

	for idx in range(5):
		store.append({"value": idx})

	records = store.read_latest()
	assert [entry["value"] for entry in records] == [4, 3, 2]


def test_get_telemetry_endpoint_returns_data(mocker, test_client):
	sample_record = {
		"request_id": "req-1",
		"source": "/videos/minio",
		"processing_mode": "sdk",
		"timestamps": {
			"requested_at": "2025-01-01T00:00:00Z",
			"completed_at": "2025-01-01T00:00:01Z",
			"wall_time_seconds": 1.0,
		},
		"video": {
			"bucket_name": "bucket",
			"video_id": "video",
			"filename": "video.mp4",
			"frame_interval": 15,
			"fps": 30.0,
			"total_frames": 300,
			"video_duration_seconds": 10.0,
			"tags": [],
			"video_url": None,
			"video_rel_url": None,
			"processing_mode": "sdk",
		},
		"config": {
			"embedding_mode": "sdk",
			"object_detection_enabled": True,
			"detection_confidence": 0.9,
			"sdk_parallel_workers": 4,
			"sdk_batch_size": 32,
		},
		"counts": {
			"frames_extracted": 20,
			"items_after_detection": 25,
			"embeddings_stored": 25,
		},
		"stages": [
			{"name": "extraction", "seconds": 0.5, "percent_of_total": 50.0},
			{"name": "detection", "seconds": 0.1, "percent_of_total": 10.0},
			{"name": "embedding", "seconds": 0.3, "percent_of_total": 30.0},
			{"name": "storage", "seconds": 0.1, "percent_of_total": 10.0},
		],
		"throughput": {
			"embeddings_per_second": 25.0,
			"wall_time_embeddings_per_second": 25.0,
			"embedding_stage_embeddings_per_second": 50.0,
			"frames_per_second": 40.0,
		},
		"batches": [],
	}

	mocker.patch(
		"src.core.telemetry.store.telemetry_store.read_latest",
		return_value=[sample_record],
	)

	response = test_client.get("/telemetry")

	assert response.status_code == 200
	payload = response.json()
	assert payload["count"] == 1
	assert payload["items"][0]["request_id"] == "req-1"