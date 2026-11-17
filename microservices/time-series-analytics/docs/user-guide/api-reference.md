# API Reference

**Version: 1.0.0**

## Stop Analytics

`POST /stop_pipeline` stops the Kapacitor daemon and all analytics tasks, but leaves
the FastAPI container running and retains the UDF configuration and assets.
The optional `expected_task_id` query parameter must match the configured UDF task;
a mismatch or missing configuration returns HTTP 409 without stopping the daemon.

A successful response is `{"status":"success","task_id":"<configured-task>"}`.
The endpoint verifies that the daemon is down before returning HTTP 200, and
repeated stops are safe. Failed shutdown verification returns HTTP 502; a backend
connection failure during shutdown returns HTTP 503.

After shutdown, `GET /health` returns HTTP 503 with
`{"status":"Kapacitor daemon is not running"}`. `GET /config?restart=false` remains
available without restarting analytics. Apply the configuration with `POST /config`
to start analytics again. Input received while Kapacitor is stopped is not replayed.

<!--hide_directive```{eval-rst}
.. swagger-plugin:: _assets/openapi.yaml
```hide_directive-->
