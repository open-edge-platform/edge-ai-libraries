# Server Management API

This document describes the server/machine management and system information
endpoints in ViPPET.

## Architecture

The servers registry runs as a **standalone service** on a central machine.
Other ViPPET instances do not expose these endpoints — they call the central
machine directly from the browser via `VITE_SERVERS_HOST`.

| Service | How to start | Default port |
|---|---|---|
| Docker (recommended) | `make run-servers` | 80 |
| Local process | `make servers` | 7861 |

Required environment variables on the central machine:
```
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/vippet_db
ADMIN_API_KEY=<your-secret-key>
```

Client machine UI `.env`:
```
VITE_SERVERS_HOST=<central-machine-ip>        # port 80 (Docker)
VITE_SERVERS_HOST=<central-machine-ip>:7861   # port 7861 (make servers)
VITE_ADMIN_API_KEY=<your-secret-key>          # omit for read-only access
```

## Authentication

Read endpoints (`GET`) are open to all callers.

Write endpoints (`POST`, `PATCH`, `DELETE`) require an `X-Admin-Key` header
matching the `ADMIN_API_KEY` set on the central server:

```
X-Admin-Key: <your-secret-key>
```

If `ADMIN_API_KEY` is not configured on the server, all write requests return
`403 Forbidden`.

## Endpoints

All endpoints are under `/api/v1/servers` unless otherwise noted.

---

### GET `/api/v1/servers/db-status`

Check whether the database is reachable and whether admin write access is
available.

**Response (200):**
```json
{
  "available": true,
  "message": "Database connection successful",
  "role": "vippet_server"
}
```

The `role` field:
- `"vippet_server"` — `ADMIN_API_KEY` is configured; UI shows the **Register Server** button.
- `"vippet_user"` — `ADMIN_API_KEY` is not set; UI hides the button (read-only).

**Response (503)** — database unreachable:
```json
{ "available": false, "message": "Cannot connect to database: ...", "role": null }
```

---

### GET `/api/v1/servers`

List all registered servers.

**Response (200):**
```json
{
  "servers": [
    {
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "ip_address": "192.168.1.100",
      "cpu_sku": "Intel Core i7-12700K",
      "ram_size": 32,
      "kernel_version": "5.15.0-56-generic"
    }
  ]
}
```

---

### POST `/api/v1/servers` 🔒

Register a new server. Requires `X-Admin-Key` header.

**Request body:**
```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "ip_address": "192.168.1.100",
  "cpu_sku": "Intel Core i7-12700K",
  "ram_size": 32,
  "kernel_version": "5.15.0-56-generic"
}
```

**Response (201):** same as request body.

**Error responses:** `400` invalid data / UUID exists · `403` missing or wrong key · `500` database error.

---

### PATCH `/api/v1/servers/{uuid}` 🔒

Partially update a registered server. Requires `X-Admin-Key` header.
Only provided fields are updated.

**Path parameter:** `uuid` — server UUID.

**Request body (all fields optional):**
```json
{ "ip_address": "192.168.1.101", "ram_size": 64 }
```

**Response (200):** full updated server object.

**Error responses:** `400` invalid values · `403` missing or wrong key · `404` UUID not found · `500` database error.

---

### DELETE `/api/v1/servers/{uuid}` 🔒

Remove a server from the registry. Requires `X-Admin-Key` header.

**Path parameter:** `uuid` — server UUID.

**Response (200):**
```json
{ "message": "Server deleted successfully" }
```

**Error responses:** `403` missing or wrong key · `404` UUID not found · `500` database error.

---

### GET `/api/v1/sysinfo`

Return hardware and OS information about the **local** ViPPET machine (the one
serving this request). Used by the UI to pre-populate the Register Server dialog.

**Response (200):**
```json
{
  "uuid": "a3c4f6e8-b2d1-c5a7-b9e0-f3a1c2d4e5f6",
  "ip_address": "192.168.1.100",
  "cpu_sku": "Intel(R) Core(TM) i7-12700K CPU @ 3.60GHz",
  "ram_size": 32,
  "kernel_version": "5.15.0-56-generic"
}
```

This endpoint is served by the **full ViPPET app** (`main.py`), not the
servers-only service.

---

## Usage Examples

### curl

```bash
BASE=http://<central-machine-ip>/api/v1
KEY=your-secret-key

# Check database status
curl $BASE/servers/db-status

# List servers
curl $BASE/servers

# Register a server (admin only)
curl -X POST $BASE/servers \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $KEY" \
  -d '{"uuid":"550e8400-e29b-41d4-a716-446655440000","ip_address":"192.168.1.100","cpu_sku":"Intel Core i7-12700K","ram_size":32,"kernel_version":"5.15.0-56-generic"}'

# Update a server (admin only)
curl -X PATCH $BASE/servers/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $KEY" \
  -d '{"ram_size": 64}'

# Remove a server (admin only)
curl -X DELETE $BASE/servers/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-Admin-Key: $KEY"

# Get local machine system info (full ViPPET app)
curl http://localhost:7860/api/v1/sysinfo
```

### Python

```python
import requests

base = "http://<central-machine-ip>/api/v1/servers"
admin_headers = {"X-Admin-Key": "your-secret-key"}

# List servers
print(requests.get(base).json())

# Register
requests.post(base, json={...}, headers=admin_headers)

# Update
requests.patch(f"{base}/550e8400-...", json={"ram_size": 64}, headers=admin_headers)

# Delete
requests.delete(f"{base}/550e8400-...", headers=admin_headers)
```

## Implementation

| Component | File | Role |
|---|---|---|
| Database ORM + session | `vippet/database.py` | SQLAlchemy models, `check_db_connection()` |
| Server CRUD logic | `vippet/managers/server_manager.py` | Thread-safe singleton, input validation |
| Servers API routes | `vippet/api/routes/servers.py` | FastAPI handlers, `ADMIN_API_KEY` auth |
| System info routes | `vippet/api/routes/sysinfo.py` | Collects local CPU/RAM/IP/kernel info |
| Central service entrypoint | `vippet/api/servers_app.py` | Minimal FastAPI app — servers router only |
| Docker service | `compose.servers.yml` | Builds and runs `Dockerfile.servers` on port 80 |
| API schemas | `vippet/api/api_schemas.py` | `ServerCreate`, `ServerUpdate`, `ServerResponse`, `ServerListResponse` |

## Interactive API Docs

Available on the central machine at:
- Swagger UI: `http://<central-machine-ip>/api/v1/docs`
- ReDoc: `http://<central-machine-ip>/api/v1/redoc`

