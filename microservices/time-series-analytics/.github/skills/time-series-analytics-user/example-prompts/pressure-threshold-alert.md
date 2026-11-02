Build a threshold-based UDF (`pressure_guard`) that flags hydraulic pressure readings outside a safe band, deployed via the Time Series Analytics microservice.

Input:
- Field: `pressure_bar` (numeric)
- Flag condition: value < 80 or value > 150
- Pattern: threshold (no model file required)

Output:
- UDF files: `pressure_guard.py`, `pressure_guard.tick`, `pressure_guard.tar`
- A point at 65 bar logs a `Flagged anomalous point` line; a point at 110 bar does not
- Verify the output of time series analytics microservice logs to confirm if it is working as expected
