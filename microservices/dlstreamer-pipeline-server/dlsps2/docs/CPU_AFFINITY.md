# DLSPS 2.0 CPU Affinity & Worker Pool

## Overview

DLSPS 2.0 now supports dynamic CPU core pinning for individual pipelines via an optional `cpu_cores` field in the start request. The implementation uses a **worker pool** where each unique CPU affinity set gets its own dedicated worker subprocess.

## Architecture

### Worker Pool Model

```
Unpinned pipelines (cpu_cores=None)
  └─ Shared long-lived worker
     (never stopped, always available)

Pinned to cores [0-3]
  └─ Dedicated worker (ephemeral)
     (auto-stops after 1 minute idle)

Pinned to cores [4-5]
  └─ Another dedicated worker (ephemeral)
     (auto-stops after 1 minute idle)
```

**Benefits:**
- ✅ True per-pipeline CPU pinning (different core sets = different workers)
- ✅ Efficiency (pipelines with same pinning share one worker)
- ✅ Auto-cleanup (ephemeral workers terminate after idle timeout)
- ✅ No resource leaks (pinned workers don't persist unnecessarily)

### Key Design Decisions

1. **Normalization:** CPU cores are normalized to sorted tuples for deduplication
   - `[2, 0, 1]` and `[0, 1, 2]` both map to key `(0, 1, 2)` → same worker

2. **Unpinned Worker Lifetime:** The unpinned worker (key=`None`) is never reaped
   - Always available for any pipeline that doesn't request specific cores
   - Survives application lifetime for efficiency

3. **Pinned Worker Lifetime:** Ephemeral workers have a 1-minute idle timeout
   - Tracked via `ManagedWorker._active_pipelines` set
   - When all pipelines complete, a timer is started
   - If no new pipelines are submitted within 60 seconds, the worker is reaped

## API Usage

### POST /pipelines (Direct Pipeline)

```bash
curl -X POST http://localhost:8080/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline": "videotestsrc ! autovideosink",
    "cpu_cores": [0, 1, 2]
  }'
```

Response:
```json
{
  "instance_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### POST /pipelines/{name}/{version} (Named Pipeline)

```bash
curl -X POST http://localhost:8080/pipelines/user_defined_pipelines/my_pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "source": {
      "uri": "file:///path/to/video.mp4"
    },
    "destination": {
      "metadata": {"type": "mqtt", "topic": "analytics"}
    },
    "cpu_cores": [4, 5]
  }'
```

### Without Pinning (Backward Compatible)

```bash
# No cpu_cores field → uses shared unpinned worker
curl -X POST http://localhost:8080/pipelines \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline": "videotestsrc ! autovideosink"
  }'
```

## Implementation Details

### Files Modified

| File | Changes | LOC |
|---|---|---|
| `src/core/worker_pool.py` | ✨ **NEW** - WorkerPool + ManagedWorker classes | ~350 |
| `src/api/schema.py` | Added `cpu_cores` field | ~3 |
| `src/core/pipeline_manager.py` | Refactored to use WorkerPool | -150 |
| `src/api/routers/pipelines.py` | Pass cpu_cores through | ~5 |

### Class Structure

#### ManagedWorker
Wraps one `gst_worker.py` subprocess with:
- stdin/stdout JSON communication
- Event handler dispatch
- Idle tracking (`_active_pipelines` set)
- Graceful shutdown
- Crash notification to the pool (no in-place restart)

#### WorkerPool
Manages a pool of ManagedWorkers:
- Dict keyed by `Optional[Tuple[int, ...]]` (normalized cpu_cores)
- Event handler callback dispatch
- Idle timeout scheduling (threading.Timer)
- Graceful multi-worker shutdown (unpinned last)

#### PipelineInstance
Now includes:
```python
cpu_cores: Optional[List[int]] = None  # Affinity for this pipeline
```

## Idle Timeout Behavior

When a pinned worker becomes idle (no active pipelines):

1. A `threading.Timer(60.0)` is scheduled
2. If a new pipeline is submitted within 60 seconds, the timer is cancelled
3. If timer fires and worker is still idle, the worker is reaped:
   - Worker subprocess receives `{"cmd": "shutdown"}`
   - Graceful shutdown with 15-second timeout
   - SIGKILL if timeout expires
   - Worker removed from pool

## Error Handling

**Invalid cpu_cores:**
- Rejected with HTTP 422 if any core is not in the server's allowed CPU set (`os.sched_getaffinity`)
- An empty list is treated as unpinned

**Worker crash:**
- All pipelines on the crashed worker are marked `ERROR` ("gst_worker process exited unexpectedly")
- The dead worker is removed from the pool; the next request for that affinity starts a fresh one
- Pipelines on other workers are unaffected

**Pinned worker after pipelines finish:**
- A pipeline is untracked on its terminal event (EOS, error, or stop)
- When the last one finishes, the worker is reaped after the idle timeout (1 minute)

## Monitoring

### Logs
Worker lifecycle events:
```
[INFO] Started gst_worker subprocess (affinity: (0, 1, 2))
[INFO] Reaped idle worker (affinity: (0, 1, 2))
[WARNING] Worker stdout closed unexpectedly (affinity: (4, 5))
[ERROR] Pipeline <id> error: gst_worker process exited unexpectedly
```

### API Status
- `GET /pipelines/status` - shows all running pipelines
- `GET /pipelines/{instance_id}` - shows individual pipeline + affinity
- Affinity is stored in `PipelineInstance.cpu_cores` for visibility

## Future Enhancements

1. **Per-Worker Metrics:** Track CPU usage per pinned worker
2. **Dynamic Rebalancing:** Move pipelines between workers based on load
3. **NUMA Support:** Enhance for NUMA-aware pinning
4. **Scheduling Policy:** Support SCHED_FIFO, SCHED_RR for real-time pipelines
5. **REST Endpoint:** Allow dynamic worker reaping via API

## References

- Linux `sched_setaffinity(2)`: https://man7.org/linux/man-pages/man2/sched_setaffinity.2.html
- Python `os.sched_setaffinity`: https://docs.python.org/3/library/os.html#os.sched_setaffinity
- GStreamer Threading: https://gstreamer.freedesktop.org/documentation/application-development/advanced/threading.html
