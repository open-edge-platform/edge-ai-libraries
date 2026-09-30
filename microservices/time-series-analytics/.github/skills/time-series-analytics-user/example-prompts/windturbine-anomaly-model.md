Develop `IsolationForest` model for wind turbine anomaly detection as a UDF (`windturbine_anomaly_detector`) via the Time Series Analytics microservice.

Input
- Field: `value` (numeric)

Output
- Container log shows `Model loaded from ...` on task start
- An out-of-distribution point (e.g. `value: 999.0`) produces a `Flagged anomalous point: value=999.0` log line
- Verify the model execution both on CPU and iGPU if supported via time series analytics microservice logs