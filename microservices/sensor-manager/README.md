# Sensor Manager

Sensor Manager is a microservice that discovers cameras available to an edge node and
describes how to stream from them:

- **USB cameras** – enumerated with `v4l2-ctl`; the best capture configuration (pixel format,
  resolution, frame rate) is selected for each `/dev/video*` capture device.
- **ONVIF network cameras** – discovered with WS-Discovery and queried for media profiles
  (RTSP URL, encoding, resolution, frame rate) using the
  [`dlstreamer.onvif`](https://github.com/open-edge-platform/dlstreamer/tree/main/python/dlstreamer/onvif)
  library.

## Quick start

```bash
make build   # build the intel/sensor-manager image
make run     # start the service (host networking, port 8090)
curl http://localhost:8090/api/v1/sensors
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Service health |
| GET | `/api/v1/sensors` | List USB and ONVIF cameras |
| GET | `/api/v1/sensors/{sensor_id}` | Get a single camera |
| POST | `/api/v1/sensors/{sensor_id}/profiles` | Load ONVIF profiles using camera credentials |

The interactive OpenAPI documentation is available at `http://<host>:8090/docs`.

## Development

```bash
make test     # unit tests
make coverage # unit tests with coverage report
make lint     # ruff lint and format check
```

See the [user guide](./docs/user-guide/index.md) for configuration and deployment details.
