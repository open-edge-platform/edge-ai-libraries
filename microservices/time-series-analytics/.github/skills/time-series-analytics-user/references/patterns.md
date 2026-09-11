<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Common Use-Case Patterns (Fast Path)

Match the user's description to a row below before writing a UDF from
scratch. Each pattern is a small delta on
[`../assets/udf_stream_template.py`](../assets/udf_stream_template.py) — the
`__init__` state and the body of `point()` are the only things that change.
Confirm the specific parameters (field name, thresholds, window size, model
file) with the user before generating code; don't guess numeric thresholds.

| Pattern | Use when the user wants to... | Needs a model file? |
|---|---|---|
| [Threshold / range check](#threshold--range-check) | flag values outside a fixed `[low, high]` band | No |
| [Rate-of-change / spike](#rate-of-change--spike-detection) | flag sudden jumps between consecutive readings | No |
| [Rolling-window statistics](#rolling-window-statistics-z-score) | flag statistical outliers relative to recent history | No (optional) |
| [Pretrained model inference](#pretrained-model-inference) | run a trained scikit-learn model per incoming point | Yes |
| [Batch windowed inference](#batch-windowed-inference) | run a model (or custom logic) over a collected time window of points | Yes (optional) |

If none of these fit (e.g. multi-field correlation, sequence modeling,
custom windowing logic), fall back to
[`udf-authoring.md`](udf-authoring.md) and write the `point()` body from
first principles — the method contract and state model are the same either
way.

## Threshold / Range Check

The simplest pattern, and what the microservice's built-in sample
(`udfs/temperature_classifier.py`) does. No `__init__` state needed.

```python
LOW, HIGH = 20.0, 25.0   # confirm actual bounds with the user

def point(self, point):
    value = point.fieldsDouble.get("value")
    if value is None:
        logger.error("Expected double field 'value' missing from point")
        return
    if value < LOW or value > HIGH:
        response = udf_pb2.Response()
        response.point.CopyFrom(point)
        self._agent.write_response(response, True)
```

## Rate-of-Change / Spike Detection

Flags points where the change from the previous reading exceeds a
threshold. Needs one instance attribute.

```python
def __init__(self, agent):
    self._agent = agent
    self.previous_value = None

def point(self, point):
    value = point.fieldsDouble.get("value")
    if value is None:
        return
    if self.previous_value is not None:
        delta = abs(value - self.previous_value)
        if delta > THRESHOLD:   # confirm THRESHOLD with the user
            response = udf_pb2.Response()
            response.point.CopyFrom(point)
            self._agent.write_response(response, True)
    self.previous_value = value   # update regardless of anomaly status
```

## Rolling-Window Statistics (Z-Score)

Flags points that deviate from the recent mean by more than N standard
deviations. Needs a bounded window; `collections.deque(maxlen=...)` is the
simplest correct choice since it evicts automatically.

```python
import collections
import statistics

WINDOW_SIZE = 30    # confirm with the user
Z_THRESHOLD = 3.0

def __init__(self, agent):
    self._agent = agent
    self.window = collections.deque(maxlen=WINDOW_SIZE)

def point(self, point):
    value = point.fieldsDouble.get("value")
    if value is None:
        return
    if len(self.window) >= WINDOW_SIZE // 2:  # need enough history to be meaningful
        mean = statistics.fmean(self.window)
        stdev = statistics.pstdev(self.window) or 1e-9
        z = (value - mean) / stdev
        if abs(z) > Z_THRESHOLD:
            response = udf_pb2.Response()
            response.point.CopyFrom(point)
            response.point.fieldsDouble["z_score"] = z
            self._agent.write_response(response, True)
    self.window.append(value)
```

For anything past a simple z-score (rolling PCA reconstruction error,
seasonal decomposition), Intel® Extension for Scikit-learn* is preinstalled
and can accelerate the heavier variants — treat this as the "pretrained
model" pattern instead once you're fitting anything.

## Pretrained Model Inference

For a model already trained offline (scikit-learn classifier, regressor,
`IsolationForest`, `OneClassSVM`, etc.), serialize it with `joblib` or
`pickle`, place the file under `models/` in the deployment package (named
starting with `<udf_name>`), and set `config.json`'s `udfs.models` to that
filename. See [`udf-authoring.md#model-loading`](udf-authoring.md#model-loading)
for the env vars this makes available.

If the user says a pretrained model file "already exists" somewhere, reuse
that exact file — don't train or fabricate a substitute. And after
deploying, confirm the model actually loaded rather than trusting a
successful REST response: see
[`udf-authoring.md#scikit-learn-version-compatibility-silent-failure-mode`](udf-authoring.md#scikit-learn-version-compatibility-silent-failure-mode)
for a real, silent failure mode (scikit-learn version mismatch between the
model's training environment and the microservice's runtime).

### Anomaly Classification (e.g., IsolationForest, OneClassSVM)

For models that output a discrete label (e.g., IsolationForest's -1 for anomaly):

```python
import os
import joblib
from sklearnex import patch_sklearn
patch_sklearn()   # accelerates predict() on CPU and Intel GPU; must precede sklearn imports

MODEL_PATH = os.environ.get("MODEL_PATH")

def __init__(self, agent):
    self._agent = agent
    self.model = joblib.load(MODEL_PATH) if MODEL_PATH else None

def point(self, point):
    value = point.fieldsDouble.get("value")
    if value is None or self.model is None:
        return
    prediction = self.model.predict([[value]])[0]
    if prediction == -1:   # convention for IsolationForest: -1 = anomaly
        response = udf_pb2.Response()
        response.point.CopyFrom(point)
        response.point.fieldsDouble["anomaly"] = 1.0
        self._agent.write_response(response, True)
```

### Anomaly Detection via Regression (e.g., RandomForestRegressor)

For regression models, compute **prediction error** as anomaly indicator:

```python
import os
import joblib
from sklearnex import patch_sklearn
patch_sklearn()   # accelerates predict() on CPU and Intel GPU; must precede sklearn imports

MODEL_PATH = os.environ.get("MODEL_PATH")
ANOMALY_THRESHOLD = 20.0  # adjust based on your data distribution

def __init__(self, agent):
    self._agent = agent
    self.model = joblib.load(MODEL_PATH) if MODEL_PATH else None

def point(self, point):
    value = point.fieldsDouble.get("value")
    if value is None or self.model is None:
        return
    
    predicted_value = self.model.predict([[value]])[0]
    error = abs(value - predicted_value)
    
    # Emit all points with anomaly field for InfluxDB analysis
    response = udf_pb2.Response()
    response.point.CopyFrom(point)
    response.point.fieldsDouble["predicted_value"] = predicted_value
    response.point.fieldsDouble["prediction_error"] = error
    response.point.fieldsDouble["anomaly"] = 1.0 if error > ANOMALY_THRESHOLD else 0.0
    self._agent.write_response(response, True)
```

**Key difference:** Regressor-based anomaly detection flags points where
the model's prediction deviates from the actual value by more than a
threshold—useful when the model learns expected/"normal" behavior.

Multi-feature models: read each input field via `point.fieldsDouble.get(...)`
and assemble the feature vector in the same order the model was trained on
— get that ordering from the user or the model's training code, don't
assume.

**sklearnex for training**: apply the same patch in your offline training
script before any sklearn import — it accelerates `fit()` on both CPU and
Intel GPU with no changes to training code:

```python
from sklearnex import patch_sklearn
patch_sklearn()
from sklearn.ensemble import IsolationForest   # or any other sklearn estimator
import joblib

model = IsolationForest(...).fit(X_train)
joblib.dump(model, "<udf_name>.pkl")   # saves a standard sklearn-compatible pickle
```

`patch_sklearn()` is transparent to pickling — the saved model loads
correctly in any environment. To target the Intel iGPU at inference time,
set `config.json`'s `udfs.device` to `"GPU"` (or `"GPU:N"`) — the resolved
value arrives as the `DEVICE` env var and sklearnex selects the device
automatically.

## Batch Windowed Inference

Use this pattern when the model (or logic) needs a *window* of consecutive
points rather than a single point — e.g., a multi-sample feature vector, a
temporal aggregation, or bulk inference for throughput. The TICKscript uses
`|window()` to collect points into fixed time windows before forwarding
them to the UDF as a batch.

**Key differences from the stream patterns above:**

- `info()` must declare `wants = udf_pb2.BATCH` (not `STREAM`).
- Implement `begin_batch(begin_req)`, `point(point)`, and
  `end_batch(end_req)` instead of only `point()`.
- Accumulate incoming points in `point()` and run inference in
  `end_batch()`. Write responses there too — the agent must emit a `begin`
  response first, then the result points, then an `end` response.

```python
def info(self):
    response = udf_pb2.Response()
    response.info.wants = udf_pb2.BATCH
    response.info.provides = udf_pb2.STREAM
    return response

def __init__(self, agent):
    self._agent = agent
    self._batch_points = []
    self._begin_response = None
    self.model = joblib.load(MODEL_PATH) if MODEL_PATH else None

def begin_batch(self, begin_req):
    self._batch_points = []
    # Capture begin to re-emit before result points.
    self._begin_response = udf_pb2.Response()
    self._begin_response.begin.CopyFrom(begin_req)

def point(self, point):
    self._batch_points.append(point)

def end_batch(self, end_req):
    if self._begin_response is not None:
        self._agent.write_response(self._begin_response)
    for point in self._batch_points:
        value = point.fieldsDouble.get("value")
        if value is not None and self.model is not None:
            pred = self.model.predict([[value]])[0]
            point.fieldsDouble["anomaly_status"] = float(pred == -1)
        response = udf_pb2.Response()
        response.point.CopyFrom(point)
        self._agent.write_response(response)
    self._batch_points = []
    end_response = udf_pb2.Response()
    end_response.end.CopyFrom(end_req)
    self._agent.write_response(end_response)
```

The tick script pairs with this via `|window()`. See
[`tickscript-basics.md#batch-windowed-udfs`](tickscript-basics.md#batch-windowed-udfs)
for the matching TICKscript.
