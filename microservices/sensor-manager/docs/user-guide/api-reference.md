# API Reference

Base path: `/api/v1`. The OpenAPI schema is served at `/openapi.json` and the interactive
documentation at `/docs`.

## GET /health

Returns `{"healthy": true}` when the service is running.

## GET /sensors

Returns all USB cameras (enumerated on each request) and ONVIF cameras (from the latest
WS-Discovery sweep). ONVIF profiles loaded earlier are preserved.

```json
[
  {
    "device_id": "usb-camera-integrated-camera-0",
    "device_name": "Integrated Camera",
    "device_type": "USB",
    "details": {
      "device_path": "/dev/video0",
      "best_capture": {"fourcc": "MJPG", "width": 1920, "height": 1080, "fps": 30.0}
    }
  },
  {
    "device_id": "network-camera-192.168.1.100-80",
    "device_name": "ONVIF Camera 192.168.1.100",
    "device_type": "NETWORK",
    "details": {"ip": "192.168.1.100", "port": 80, "profiles": [], "best_profile": null}
  }
]
```

| Code | Description |
|------|-------------|
| 200 | List of sensors (possibly empty) |
| 500 | `{"message": "..."}` – unexpected error |

## GET /sensors/{sensor_id}

Returns a single sensor. If the sensor is not cached yet, discovery is refreshed once.

| Code | Description |
|------|-------------|
| 200 | Sensor |
| 404 | Sensor not found |
| 422 | Invalid `sensor_id` (allowed characters: `A-Z a-z 0-9 . _ : -`, max. 256) |

## POST /sensors/{sensor_id}/profiles

Connects to an ONVIF camera and reads its media profiles.

Request body (`username` and `password` up to 256 characters each):

```json
{"username": "<user>", "password": "<password>"}
```

Response:

```json
{
  "camera": {
    "device_id": "network-camera-192.168.1.100-80",
    "device_name": "ONVIF Camera 192.168.1.100",
    "device_type": "NETWORK",
    "details": {
      "ip": "192.168.1.100",
      "port": 80,
      "profiles": [
        {
          "name": "MainStream",
          "rtsp_url": "rtsp://192.168.1.100:554/stream1",
          "resolution": "1920x1080",
          "encoding": "H264",
          "framerate": 30,
          "bitrate": 4096
        }
      ],
      "best_profile": {
        "name": "MainStream",
        "rtsp_url": "rtsp://192.168.1.100:554/stream1",
        "resolution": "1920x1080",
        "encoding": "H264",
        "framerate": 30,
        "bitrate": 4096
      }
    }
  }
}
```

| Code | Description |
|------|-------------|
| 200 | Profiles loaded |
| 400 | `sensor_id` is not a valid network camera identifier |
| 401 | Credentials rejected by the camera |
| 404 | Camera not discovered or not reachable |
| 422 | Invalid request body |
| 500 | Unexpected ONVIF error |
