# API Reference

## Health Check

Endpoint:

```bash
GET /v1/retrieval/health
```

**Description:**

Checks the health status of the microservice.

**Response:**

- 200 OK:

  ```json
  {
      "status": "healthy"
  }
  ```

- 500 Internal Server Error:

  ```json
  {
      "detail": "Health check failed: <error_message>"
  }
  ```

## Retrieval

Endpoint:

```bash
POST /v1/retrieval
```

**Description:**

Performs a retrieval task using the provided text query and optional filters.

**Request Body:**

```json
{
    "query": "<text_query>",
    "filter": {
        "<key>": "<value>"
    },
    "max_num_results": 10
}
```

- ``query``: The text query for retrieval.
- ``filter``: Optional dictionary to refine search results.
- ``max_num_results``: Maximum number of results to return (default: 10).

**Response:**

- 200 OK:

  ```text
  {
      "results": [
          {
              "id": "<result_id>",
              "distance": <similarity_score>,
              "meta": {
                  "<key>": "<value>"
              }
          },
          ...
      ]
  }
  ```

- 500 Internal Server Error:

  ```json
  {
      "detail": "Error during retrieval: <error_message>"
  }
  ```
