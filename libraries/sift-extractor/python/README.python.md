# sift-extractor (Python)

Thin binary wheel for the Intel SIFT extractor. **`pip install` does not install the GPU stack.**

## System requirements (not provided by this package)

| Need | Purpose |
| --- | --- |
| Intel GPU driver with compute | Device access |
| OpenCL ICD (`libOpenCL.so.1`) | OpenCL backend |
| Intel oneAPI SYCL + Level Zero runtimes | SYCL backend (often `source /opt/intel/oneapi/setvars.sh`) |

Install those for your OS first, then install this wheel.

## Install

```bash
# After the GPU stack is available on this host:
pip install sift_extractor-*.whl
# or: pip install /path/to/dist/sift_extractor-0.1.0-*.whl
```

## Quick start

```python
import numpy as np
import sift_extractor

print(sift_extractor.__version__)
print(sift_extractor.system_requirements())
print(sift_extractor.available_backends())

ext = sift_extractor.Extractor(64, 64, backend="auto")
features = ext.extract(np.zeros((64, 64), dtype=np.float32))
print(len(features), ext.backend)
```

If import fails with a missing `.so`, the host stack/loader path is incomplete — fix the driver/runtime, not pip.
