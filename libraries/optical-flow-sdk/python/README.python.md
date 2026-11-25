<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# optical-flow-sdk (Python)

Facade APIs match C++: pick `backend` / `algorithm` / `preset` — do not use
OpenCL/SYCL types from Python.

## Install (wheel)

From the SDK root (CPU-only wheel; native code linked into `_native`):

```bash
python3 -m pip install .
# or: ./scripts/build_wheel.sh && pip install dist/*.whl
```

## Install (Debian)

```bash
sudo apt install python3-optical-flow-sdk
# samples: /usr/share/optical-flow-sdk/python-samples/
```

## Build module in-tree (developers)

```bash
cmake -S . -B build \
  -DOPTICALFLOW_ENABLE_CPU=ON \
  -DOPTICALFLOW_BUILD_PYTHON=ON
cmake --build build --parallel
# _native lands in python/optical_flow_sdk/; add python/ to PYTHONPATH
PYTHONPATH=python python3 python/samples/calc_flow_dis.py
```

## Minimal usage

```python
import numpy as np
from optical_flow_sdk import OpticalFlow, SparsePyrLK, SparsePyrLKOptions

prev = np.zeros((64, 64), dtype=np.uint8)
next = np.zeros((64, 64), dtype=np.uint8)
of = OpticalFlow(backend="auto", preset="fast", algorithm="dis")
flow, _ = of.calc(prev, next)

opts = SparsePyrLKOptions()
lk = SparsePyrLK(opts, backend="auto")
```

Samples: `python/samples/` (`calc_flow_dis.py`, `calc_flow_farneback.py`,
`track_points.py`).
