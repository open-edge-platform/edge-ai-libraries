# Server Management API Endpoints

This document describes the new server/machine management endpoints added to ViPPET.

## Overview

The server management API allows you to track and manage information about machines/servers in your infrastructure. Each server record stores:

- **UUID**: Unique identifier
- **IP Address**: Network address
- **CPU SKU**: CPU model/identifier
- **RAM Size**: Memory in GB
- **Kernel Version**: Ubuntu kernel version

## API Endpoints

All endpoints are under `/api/v1/servers`

### 1. Add Server

**POST** `/api/v1/servers`

Add a new server to the database.

**Request Body:**
```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "ip_address": "192.168.1.100",
  "cpu_sku": "Intel Core i7-12700K",
  "ram_size": 32,
  "kernel_version": "5.15.0-56-generic"
}
```

**Response (201 Created):**
```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "ip_address": "192.168.1.100",
  "cpu_sku": "Intel Core i7-12700K",
  "ram_size": 32,
  "kernel_version": "5.15.0-56-generic"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid data or UUID already exists
- `500 Internal Server Error`: Database error

### 2. List Servers

**GET** `/api/v1/servers`

Retrieve all servers in the database.

**Response (200 OK):**
```json
{
  "servers": [
    {
      "uuid": "550e8400-e29b-41d4-a716-446655440000",
      "ip_address": "192.168.1.100",
      "cpu_sku": "Intel Core i7-12700K",
      "ram_size": 32,
      "kernel_version": "5.15.0-56-generic"
    },
    {
      "uuid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "ip_address": "192.168.1.101",
      "cpu_sku": "Intel Core i9-12900K",
      "ram_size": 64,
      "kernel_version": "5.19.0-50-generic"
    }
  ]
}
```

### 3. Update Server

**PATCH** `/api/v1/servers/{uuid}`

Update server details (partial update - only provided fields are updated).

**Path Parameters:**
- `uuid`: Server UUID

**Request Body (all fields optional):**
```json
{
  "ip_address": "192.168.1.101",
  "ram_size": 64
}
```

**Response (200 OK):**
```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "ip_address": "192.168.1.101",
  "cpu_sku": "Intel Core i7-12700K",
  "ram_size": 64,
  "kernel_version": "5.15.0-56-generic"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid field values
- `404 Not Found`: Server with given UUID not found
- `500 Internal Server Error`: Database error

### 4. Delete Server

**DELETE** `/api/v1/servers/{uuid}`

Remove a server from the database.

**Path Parameters:**
- `uuid`: Server UUID

**Response (200 OK):**
```json
{
  "message": "Server deleted successfully"
}
```

**Error Responses:**
- `404 Not Found`: Server with given UUID not found
- `500 Internal Server Error`: Database error

## Usage Examples

### Using curl

```bash
# Add a server
curl -X POST http://localhost:7860/api/v1/servers \
  -H "Content-Type: application/json" \
  -d '{
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "ip_address": "192.168.1.100",
    "cpu_sku": "Intel Core i7-12700K",
    "ram_size": 32,
    "kernel_version": "5.15.0-56-generic"
  }'

# List all servers
curl http://localhost:7860/api/v1/servers

# Update a server
curl -X PATCH http://localhost:7860/api/v1/servers/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{
    "ram_size": 64
  }'

# Delete a server
curl -X DELETE http://localhost:7860/api/v1/servers/550e8400-e29b-41d4-a716-446655440000
```

### Using Python requests

```python
import requests

base_url = "http://localhost:7860/api/v1/servers"

# Add a server
response = requests.post(base_url, json={
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "ip_address": "192.168.1.100",
    "cpu_sku": "Intel Core i7-12700K",
    "ram_size": 32,
    "kernel_version": "5.15.0-56-generic"
})
print(response.json())

# List servers
response = requests.get(base_url)
print(response.json())

# Update server
uuid = "550e8400-e29b-41d4-a716-446655440000"
response = requests.patch(f"{base_url}/{uuid}", json={
    "ram_size": 64
})
print(response.json())

# Delete server
response = requests.delete(f"{base_url}/{uuid}")
print(response.json())
```

## Database Storage

Server data is stored in a SQLite database at `/database/vippet.db` inside the container (mounted from `./shared/database/vippet.db` on the host, configurable via `DB_DIR` environment variable).

The database is automatically initialized on application startup. The database directory is created during `make env-setup`.

## Implementation Details

### Components

1. **Database Module** (`vippet/database.py`)
   - SQLAlchemy ORM models
   - Database session management
   - Server table schema

2. **Server Manager** (`vippet/managers/server_manager.py`)
   - Thread-safe singleton pattern
   - Business logic for CRUD operations
   - Input validation

3. **API Routes** (`vippet/api/routes/servers.py`)
   - FastAPI route handlers
   - Request/response validation
   - Error handling

4. **API Schemas** (`vippet/api/api_schemas.py`)
   - Pydantic models for request/response validation
   - `ServerCreate`, `ServerUpdate`, `ServerResponse`, `ServerListResponse`

### Validation Rules

- All fields must be non-empty strings (except `ram_size` which is an integer)
- `ram_size` must be a positive integer
- `uuid` must be unique across all servers
- Updates validate only provided fields

## API Documentation

Full interactive API documentation is available at:
- Swagger UI: http://localhost:7860/api/v1/docs
- ReDoc: http://localhost:7860/api/v1/redoc
