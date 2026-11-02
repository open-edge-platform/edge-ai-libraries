A UDF deployment package was uploaded and `POST /config` returned 200, but the container logs show no sign of the task running and `POST /input` data isn't producing any flagged output. Figure out why and fix it.

- Start from `docker logs -f ia-time-series-analytics-microservice` and, if needed, `docker exec -it ia-time-series-analytics-microservice bash` then `cat /tmp/log/kapacitor/kapacitor.log | grep -i error` — this is where `classifier_startup.py`'s `enable_classifier_task` retries and Kapacitor daemon errors surface.
- Cross-check `src/classifier_startup.py`'s `check_udf_package` requirements against what's actually on disk under `/tmp/<name>/` (exact filename matches for `udfs/<name>.py` and `tick_scripts/<name>.tick`, and a `models/<name>*` file if `udfs.models` is set).
- Consider the tick script's `.measurement(...)` vs. what `POST /input`'s `topic` actually sends — a mismatch here doesn't error, it just means zero points ever reach the UDF node.

Validate the fix using:
- Reproduce first: deploy a package with a deliberately wrong tick-script measurement name against a running dev instance, confirm `POST /input` produces no visible effect.
- After the fix (or after identifying it as a user-config issue rather than a service bug), confirm `docker logs` shows the UDF receiving and flagging points as expected.

Expected results:
- A clear diagnosis of which of the two failure classes it is (deployment package structurally invalid vs. tick-script/measurement mismatch vs. an actual bug in `main.py`/`classifier_startup.py`), backed by the specific log line or file-check that confirms it.
- If it's a genuine service bug (not a user config mistake), a fix with a regression test added per `references/testing.md`.
