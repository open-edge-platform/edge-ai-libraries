<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# DLS-PS Federation Proxy

A lightweight federation proxy that presents multiple DLS-PS instances across physical NUCs as a single unified system. Clients interact with one API endpoint and the proxy handles scheduling, routing, and aggregation transparently.

```
┌─────────────────────────────────────────────────────────────┐
│  Client Application                                         │
│  curl http://nuc-controller:8080/pipelines/status           │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  Federation Proxy        │
              │  (Controller NUC :8080)  │
              └──┬─────────┬─────────┬──┘
                 │         │         │
          ┌──────▼──┐ ┌────▼────┐ ┌──▼──────┐
          │ DLS-PS  │ │ DLS-PS  │ │ DLS-PS  │
          │ :8081   │ │ :8080   │ │ :8080   │
          │Controller│ │Worker-1 │ │Worker-2 │
          └─────────┘ └─────────┘ └─────────┘
```

## Prerequisites

Every NUC (controller and workers) needs:

- Docker Engine 24+ and Docker Compose v2
- Network connectivity between all NUCs (port 8080 open)
- (Optional) SSH key-based auth from controller to workers for remote restart

## 1. Set Up Worker NUCs

On **each worker NUC**, start a DLS-PS instance. No other software is required.

### Worker NUC 1 (192.168.1.101)

```bash
# Pull and start DLS-PS
docker run -d \
  --name dlstreamer-pipeline-server \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /home/user/pipelines:/home/pipeline-server/pipelines:ro \
  -v /home/user/models:/home/pipeline-server/models:ro \
  --device /dev/dri:/dev/dri \
  intel/dlstreamer-pipeline-server:latest

# Verify it's running
curl http://localhost:8080/pipelines
```

### Worker NUC 2 (192.168.1.102)

```bash
# Same as above
docker run -d \
  --name dlstreamer-pipeline-server \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /home/user/pipelines:/home/pipeline-server/pipelines:ro \
  -v /home/user/models:/home/pipeline-server/models:ro \
  --device /dev/dri:/dev/dri \
  intel/dlstreamer-pipeline-server:latest
```

### Pipeline Template Setup

Each DLS-PS instance needs pipeline templates on disk. For example, to enable
the `object_detection/1` pipeline used in the examples below, create this file
on every NUC at `/home/user/pipelines/object_detection/1/pipeline.json`:

```json
{
  "type": "GStreamer",
  "template": [
    "urisourcebin uri={source[uri]} !",
    "decodebin3 !",
    "gvadetect model={models[object_detection][yolo11n][INT8]} device={parameters[detection-device]} !",
    "queue !",
    "gvafpscounter !",
    "appsink name=appsink"
  ],
  "description": "Object detection with YOLOv11n",
  "parameters": {
    "detection-device": {
      "default": "GPU",
      "type": "string"
    }
  }
}
```

## 2. Set Up the Controller NUC

The controller runs both a local DLS-PS instance and the federation proxy.

### Step 2a: Configure node registry

Edit `nodes.yaml` with the actual IPs of your NUCs:

```yaml
nodes:
  - id: nuc-controller
    url: http://localhost:8081          # Local DLS-PS on this machine
    max_pipelines: 50
    ssh: null

  - id: nuc-worker-1
    url: http://192.168.1.101:8080     # Worker NUC 1
    max_pipelines: 50
    ssh: user@192.168.1.101            # Optional: for remote restart

  - id: nuc-worker-2
    url: http://192.168.1.102:8080     # Worker NUC 2
    max_pipelines: 50
    ssh: user@192.168.1.102

health_check_interval: 10
request_timeout: 5.0
```

### Step 2b: Start with Docker Compose (recommended)

```bash
cd microservices/dlstreamer-pipeline-server/federation

# Build and start both the proxy and local DLS-PS
docker compose -f docker/docker-compose.yml up -d

# Verify
curl http://localhost:8080/nodes
```

### Step 2b (alternative): Start containers individually

```bash
# 1. Start local DLS-PS on port 8081
docker run -d \
  --name dlstreamer-pipeline-server \
  -p 8081:8080 \
  -v /home/user/pipelines:/home/pipeline-server/pipelines:ro \
  -v /home/user/models:/home/pipeline-server/models:ro \
  --device /dev/dri:/dev/dri \
  intel/dlstreamer-pipeline-server:latest

# 2. Build the federation proxy
docker build -t dlsps-federation-proxy .

# 3. Run the federation proxy on port 8080
docker run -d \
  --name federation-proxy \
  --network host \
  -v $(pwd)/nodes.yaml:/app/nodes.yaml:ro \
  dlsps-federation-proxy
```

## 3. Verify the Federation

```bash
PROXY=http://nuc-controller:8080

# List all registered nodes and their health
curl $PROXY/nodes
# [
#   {"id": "nuc-controller", "url": "http://localhost:8081", "max_pipelines": 50, "healthy": true},
#   {"id": "nuc-worker-1", "url": "http://192.168.1.101:8080", "max_pipelines": 50, "healthy": true},
#   {"id": "nuc-worker-2", "url": "http://192.168.1.102:8080", "max_pipelines": 50, "healthy": true}
# ]

# List available pipeline templates (deduplicated across all nodes)
curl $PROXY/pipelines
# [
#   {"name": "object_detection", "version": "1", "type": "GStreamer", "description": "Object detection with YOLOv11n", ...}
# ]
```

## 4. Usage Examples

### Start a pipeline (auto-scheduled)

The proxy picks the least-loaded node automatically:

```bash
curl -X POST $PROXY/pipelines/object_detection/1 \
  -H "Content-Type: application/json" \
  -d '{
    "source": {
      "type": "uri",
      "uri": "file:///home/user/videos/video1.mp4"
    },
    "destination": {
      "metadata": {
        "type": "file",
        "path": "/tmp/results.json"
      }
    },
    "parameters": {
      "detection-device": "GPU"
    }
  }'

# Response: "nuc-worker-1:1"
# The composite ID tells you it was scheduled to nuc-worker-1, instance 1
```

### Start multiple pipelines across the cluster

```bash
# Start 4 pipelines — the proxy distributes them across nodes
for i in 1 2 3 4; do
  echo "Starting pipeline $i..."
  curl -s -X POST $PROXY/pipelines/object_detection/1 \
    -H "Content-Type: application/json" \
    -d "{
      \"source\": {\"type\": \"uri\", \"uri\": \"file:///home/user/videos/video${i}.mp4\"},
      \"parameters\": {\"detection-device\": \"GPU\"}
    }"
  echo ""
done

# Example output:
# "nuc-controller:1"
# "nuc-worker-1:1"
# "nuc-worker-2:1"
# "nuc-controller:2"     ← wraps back to least-loaded
```

### Check status of all pipelines across all nodes

```bash
curl $PROXY/pipelines/status

# [
#   {"id": "nuc-controller:1", "state": "RUNNING", "avg_fps": 30.1, "node": "nuc-controller"},
#   {"id": "nuc-worker-1:1",   "state": "RUNNING", "avg_fps": 29.8, "node": "nuc-worker-1"},
#   {"id": "nuc-worker-2:1",   "state": "RUNNING", "avg_fps": 30.5, "node": "nuc-worker-2"},
#   {"id": "nuc-controller:2", "state": "RUNNING", "avg_fps": 28.2, "node": "nuc-controller"}
# ]
```

### Check status of a specific pipeline

```bash
curl $PROXY/pipelines/nuc-worker-1:1/status

# {"id": "nuc-worker-1:1", "state": "RUNNING", "avg_fps": 29.8, "node": "nuc-worker-1"}
```

### Get pipeline instance details

```bash
curl $PROXY/pipelines/nuc-worker-1:1

# {"id": "nuc-worker-1:1", "type": "GStreamer", "request": {...}, "node": "nuc-worker-1"}
```

### Stop a pipeline

```bash
curl -X DELETE $PROXY/pipelines/nuc-worker-1:1

# {"state": "ABORTED"}
```

### Stop all pipelines

```bash
# Get all running pipeline IDs and delete them
curl -s $PROXY/pipelines/status | \
  python3 -c "import sys,json; [print(p['id']) for p in json.load(sys.stdin)]" | \
  xargs -I{} curl -s -X DELETE $PROXY/pipelines/{}
```

## 5. Configuration Reference

### nodes.yaml

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `nodes[].id` | string | required | Unique node identifier |
| `nodes[].url` | string | required | DLS-PS base URL |
| `nodes[].max_pipelines` | int | 50 | Max concurrent pipelines (capacity hint) |
| `nodes[].ssh` | string | null | SSH target for remote restart (e.g., `user@host`) |
| `health_check_interval` | int | 10 | Seconds between health polls |
| `request_timeout` | float | 5.0 | HTTP timeout for proxied requests (seconds) |

### Proxy CLI arguments

```
python -m src [OPTIONS]

  --config PATH      Path to nodes.yaml (default: nodes.yaml)
  --host HOST        Listen address (default: 0.0.0.0)
  --port PORT        Listen port (default: 8080)
  --log-level LEVEL  debug, info, warning, error (default: info)
```

## 6. API Reference

All standard DLS-PS endpoints are supported. The proxy adds the `/nodes` endpoint.

| Method | Endpoint | Behavior |
|--------|----------|----------|
| `GET` | `/pipelines` | Deduplicated templates from all nodes |
| `POST` | `/pipelines/{name}/{version}` | Schedule to least-loaded node, returns composite ID |
| `GET` | `/pipelines/status` | Aggregated status from all nodes |
| `GET` | `/pipelines/{composite_id}` | Routed to owning node |
| `GET` | `/pipelines/{composite_id}/status` | Routed to owning node |
| `DELETE` | `/pipelines/{composite_id}` | Stop pipeline on owning node |
| `POST` | `/pipelines/{name}/{version}/{composite_id}` | Forward request to instance |
| `POST` | `/pipelines/{name}/{version}/{composite_id}/models` | Forward model download |
| `GET` | `/nodes` | List nodes with health status (federation-specific) |

Composite IDs have the format `{node_id}:{instance_id}` (e.g., `nuc-worker-1:42`).

## 7. Scheduling Algorithm

When a client sends `POST /pipelines/{name}/{version}`, the proxy decides which node runs it using **least-loaded scheduling with capacity awareness**.

### How it works

```
1. For each node in nodes.yaml:
   → GET {node.url}/pipelines/status
   → Count pipelines with state == "RUNNING"

2. Filter out:
   - Nodes that didn't respond (unhealthy)
   - Nodes at capacity (running >= max_pipelines)

3. Sort remaining by utilization ratio:
   utilization = running_count / max_pipelines

4. Pick the node with the lowest utilization
```

### Example

```
nodes.yaml:
  nuc-controller:  max_pipelines=50
  nuc-worker-1:    max_pipelines=50
  nuc-worker-2:    max_pipelines=30

Current state:
  nuc-controller:  20 running → 20/50 = 40%
  nuc-worker-1:    10 running → 10/50 = 20%  ← lowest utilization, wins
  nuc-worker-2:    15 running → 15/30 = 50%

→ New pipeline goes to nuc-worker-1
```

### Key properties

| Property | Behavior |
|----------|----------|
| **Real-time** | Queries actual load from each node at scheduling time — no stale cache |
| **Capacity-aware** | Respects `max_pipelines` per node — heterogeneous hardware supported |
| **Fault-tolerant** | Unreachable nodes are skipped, not retried |
| **No persistence** | No database — if the proxy restarts, it re-discovers state from nodes |

### Current limitations

- **No pipeline migration** — once started on a node, it stays there
- **No resource-based scheduling** — doesn't consider GPU/CPU/memory utilization, only pipeline count
- **No affinity/anti-affinity** — can't pin specific pipeline types to specific nodes
- **No queuing** — if all nodes are full, returns HTTP 503 immediately

These are listed as future extensions in the concept. For the demo, pipeline count is a sufficient proxy for load since all NUCs have identical hardware.

## 8. Troubleshooting

**Proxy returns 503 "No healthy nodes"**
- Check that all DLS-PS instances are running: `curl http://<worker-ip>:8080/pipelines`
- Check node health: `curl http://nuc-controller:8080/nodes`
- Verify `nodes.yaml` has correct IPs

**Pipeline starts but no video output**
- Ensure the video file path exists inside the DLS-PS container
- Ensure models are mounted and paths match the pipeline template

**Node shows unhealthy but DLS-PS is running**
- Check firewall rules — port 8080 must be reachable from the controller
- Check `request_timeout` in `nodes.yaml` — increase if network is slow

## 9. Development

```bash
# Create venv and install deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run locally
python -m src --config nodes.yaml --log-level debug

# Run tests
pip install pytest pytest-asyncio respx
make test

# Build Docker image
make build
```
