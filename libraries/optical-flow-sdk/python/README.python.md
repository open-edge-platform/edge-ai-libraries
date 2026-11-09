<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# optical-flow-sdk (Python)

Build the native module from the library tree:

```bash
cmake -S .. -B ../build \
  -DOPTICALFLOW_ENABLE_CPU=ON \
  -DOPTICALFLOW_BUILD_PYTHON=ON \
  -DOPTICALFLOW_ENABLE_SYCL=OFF \
  -DOPTICALFLOW_ENABLE_OPENCL=OFF
cmake --build ../build --parallel
```

Copy or install `_native.*` next to `optical_flow_sdk/`, then:

```python
import numpy as np
from optical_flow_sdk import OpticalFlow

prev = np.zeros((64, 64), dtype=np.uint8)
next = np.zeros((64, 64), dtype=np.uint8)
of = OpticalFlow(backend="cpu", preset="fast")
flow, _ = of.calc(prev, next)
```
