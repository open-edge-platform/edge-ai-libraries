<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Test / demo harness

Exercises the REST side of the `encoder` / `decoder` roles (see the main
README) end-to-end: multiple sender clients,
multiple receiver clients, a docker-compose stack, and a scaling benchmark.

`--role encoder` / `--role decoder` (main.py) always run the legacy batch TCP
mode alongside the REST service; this harness focuses on the REST side.

## 1. Get sample input data

```bash
python tests/sample_data/fetch_sample_data.py            # synthetic, offline, deterministic
# or, for more realistic photo content (needs network):
python tests/sample_data/fetch_sample_data.py --source picsum --count 20
```

Writes JPEGs to `tests/sample_data/images/`.

## 2. Fast in-process smoke tests (no docker)

```bash
pip install -r requirements.txt
pytest tests/test_rest_api.py -v
```

Runs the encoder/decoder FastAPI apps in-process (`TestClient`) to check stream
creation, the decode round trip, multi-consumer fan-out, and encoder→decoder
forwarding — no real network, no YOLO weights needed.

## 3. Full docker-compose demo (multiple containers, real HTTP)

```bash
docker compose -f tests/docker-compose.yml up --build --scale sender=2 --scale receiver=2
```

Brings up:
- `encoder` (REST service, port 8001 on the host)
- `decoder` (REST service, port 8002 on the host)
- `sender` × N — reads `tests/sample_data/images/`, POSTs frames to the encoder
- `receiver` × M — polls the decoder, writes decoded JPEGs to `./received` inside
  each receiver container

All senders/receivers default to the same `demo-stream`. Scaling `receiver`
demonstrates the pub/sub fan-out: every receiver replica ends up with the full
set of decoded frames independently (each tracks its own cursor), not a
partitioned subset.

Stop with `docker compose -f tests/docker-compose.yml down`.

## 4. Running a single sample client manually

```bash
python tests/sample_clients/sender_client.py --encoder-url http://localhost:8001 --stream-id demo-stream --fps 2
python tests/sample_clients/receiver_client.py --decoder-url http://localhost:8002 --stream-id demo-stream --output-dir ./received
```

## 5. Performance / scaling benchmark

With the compose stack up (or any other reachable encoder/decoder pair):

```bash
python tests/perf/benchmark.py \
    --encoder-url http://localhost:8001 --decoder-url http://localhost:8002 \
    --concurrency-levels 1,2,4,8 --frames-per-sender 20 \
    --csv results.csv --plot results.png
```

Sweeps sender/receiver concurrency, reporting submit latency, end-to-end
latency (submit → decoded frame received), throughput, and error rate per
level. The encoder/decoder REST services have no separate worker-pool knob to
tune -- each stream's blocking work runs via `asyncio.to_thread`, so
concurrent-client throughput scales with the number of concurrently open
streams rather than a fixed pool size.
