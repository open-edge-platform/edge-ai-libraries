Build a rate-of-change UDF (`vibration_spike_detector`) that flags sudden motor vibration spikes and publishes an MQTT alert, deployed via the Time Series Analytics microservice.

Input:
- Field: `vibration_mm_s` (numeric)
- Flag condition: delta from previous reading > 5 mm/s
- Pattern: rate-of-change (`previous_value` instance attribute, no model file)
- MQTT broker (`eclipse-mosquitto`) on the same Docker network; broker named `motor_alerts_broker` in `config.json`

Output:
- UDF files: `vibration_spike_detector.py`, `vibration_spike_detector.tick`, `vibration_spike_detector.tar`
- Sequence 2.0 → 2.1 → 9.5 → 9.6: only the 9.5 point triggers an MQTT alert; 9.6 does not
- Confirmed by `mosquitto_sub` showing exactly one message on the alert topic
- Verify the output of time series analytics microservice logs to confirm if it is working as expected
