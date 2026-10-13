# API Reference

**Version: 1.0.0**

## Pipeline status

`GET /pipeline_status` returns the configured UDF task's Kapacitor status without changing it.
Pass `expected_task_id` as an optional query parameter to require that the configured task matches.

For example, `GET /pipeline_status?expected_task_id=weld_anomaly_detector` returns:

```json
{"task_id": "weld_anomaly_detector", "status": "enabled"}
```

The status may also be `disabled`. The endpoint returns HTTP 409 when no task is configured or
the expected task does not match, 502 when Kapacitor rejects the request, and 503 when it is unavailable.

<!--hide_directive```{eval-rst}
.. swagger-plugin:: _assets/openapi.yaml
```hide_directive-->
