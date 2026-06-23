# Troubleshooting

## Service Will Not Start

- **Port Conflict**: Confirm that port `8080` (API) or `9090` (metrics) is not already in use:
  ```bash
  ss -ltnp | grep 8080
  ss -ltnp | grep 9090
  ```
- **Missing VLM Variables**: If `DEFAULT_MATCHING_STRATEGY` is `semantic` or `hybrid`, the service will log an error at startup if the required VLM variables are missing. Check startup logs:
  ```bash
  make docker-logs
  ```
  For OVMS, ensure `OVMS_ENDPOINT` and `OVMS_MODEL_NAME` are set in `.env`. For `openvino_local`, ensure `OPENVINO_MODEL_PATH` points to an accessible directory. For `openai`, ensure `OPENAI_API_KEY` is set.
- **Invalid `.env`**: Verify `.env` exists and has no syntax errors. The service silently falls back to defaults for missing keys, but completely absent `.env` files will use all defaults — including an empty `OVMS_ENDPOINT`.

## Health Endpoint Fails

- **Docker run**: Use `make docker-logs` or `docker compose -f docker/docker-compose.yml ps` to inspect startup errors.
- **Proxy blocks**: If behind a corporate proxy, `curl` hitting `localhost` may be blocked. Add `--noproxy '*'`:
  ```bash
  curl --noproxy '*' http://localhost:8080/api/v1/health
  ```

## Semantic or Hybrid Matching Returns No Matches

- **Wrong Strategy**: Check that `DEFAULT_MATCHING_STRATEGY` in `.env` is `semantic` or `hybrid`, not `exact`.
- **VLM Backend Unavailable**: The health endpoint reports `vlm_status`. If it shows `"unavailable"`, the backend is misconfigured or unreachable. Check `OVMS_ENDPOINT` connectivity from inside the container:
  ```bash
  docker exec semantic-search-agent curl -s ${OVMS_ENDPOINT}/v3/models
  ```
- **Confidence Threshold Too High**: If the VLM returns YES but matches are still rejected, the confidence score may be below `CONFIDENCE_THRESHOLD` (default `0.85`). Lower the threshold or use the `/compare/semantic` endpoint to inspect raw responses.
- **Cache Stale**: If you recently changed configuration but are getting cached results, clear the cache by restarting the service (in-memory cache) or flushing Redis:
  ```bash
  docker exec semantic-redis redis-cli FLUSHDB
  ```

## OVMS Connection Errors

- **Wrong Endpoint Format**: `OVMS_ENDPOINT` must be a full base URL without a trailing slash, e.g. `http://ovms-host:8000`. The service appends `/v3/chat/completions` automatically.
- **Proxy Interference**: The OVMS backend bypasses system proxy variables (`trust_env=False`) to avoid routing internal OVMS traffic through a corporate proxy. If your OVMS server requires proxy access, set `NO_PROXY` or adjust the backend configuration.
- **Model Not Loaded**: Confirm the model specified in `OVMS_MODEL_NAME` is actually loaded in OVMS:
  ```bash
  curl http://<ovms-host>:8000/v3/models
  ```

## Order Validation Returns Unexpected Results

- **Normalization Differences**: The ExactMatcher normalizes text (lowercase, whitespace trim, special character removal) before comparison. Inputs like `"Coca-Cola"` and `"coca cola"` will match. If you expect case-sensitive behavior, set `CONFIDENCE_THRESHOLD=1.0` and use the `exact` strategy only.
- **Quantity Mismatch Not Reported**: Items with matching names but different quantities appear in `validation.quantity_mismatch`, not in `validation.missing`. Check both arrays in the response.
- **Items Appear in Both Missing and Extra**: This indicates the names are semantically different from the service's perspective. Use `/compare/semantic` to diagnose the VLM response directly for the specific pair.

## High Latency on Semantic Requests

- **Cache Disabled**: Confirm `CACHE_ENABLED=true` in `.env`. Without caching, every unique pair triggers a VLM inference call.
- **OVMS Overloaded**: If OVMS has high load, latency increases. Monitor OVMS metrics and consider increasing `OVMS_TIMEOUT` for slow responses.
- **Use Hybrid Strategy**: With `DEFAULT_MATCHING_STRATEGY=hybrid`, exact matches are resolved without any VLM call, significantly reducing latency for items with consistent naming.

## Supporting Resources

- [Configuration Guide](./get-started/configuration.md)
- [API Reference](./api-reference.md)
- [System Requirements](./get-started/system-requirements.md)
- [How It Works](./how-it-works.md)
