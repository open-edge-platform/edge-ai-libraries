<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Python samples

Requires a built `optical_flow_sdk` package (`pip install` wheel, or CMake
`-DOPTICALFLOW_BUILD_PYTHON=ON`).

```bash
# From a wheel / editable install:
python3 calc_flow_dis.py
python3 calc_flow_farneback.py
python3 track_points.py
```

All samples use the facade (`backend="auto"` / `"cpu"`), not OpenCL/SYCL types.
