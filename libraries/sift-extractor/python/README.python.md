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

Real-image extract + match sample (recommended):

```bash
python python/samples/extract_and_match.py scene.pgm          # affine pair + match
python python/samples/extract_and_match.py left.png right.png # two views + match
```

PNG/JPEG need OpenCV or Pillow; binary `.pgm` works with NumPy only.
A single image builds a 30° / 0.85 affine pair (needs OpenCV for `warpAffine`) then matches.

Library usage:

```python
import numpy as np
import sift_extractor

print(sift_extractor.__version__)
print(sift_extractor.system_requirements())
print(sift_extractor.available_backends())

ext = sift_extractor.Extractor(image1.shape[1], image1.shape[0], backend="auto")
feats1 = ext.extract(image1)
ext2 = sift_extractor.Extractor(image2.shape[1], image2.shape[0], backend=ext.backend)
feats2 = ext2.extract(image2)
matches = sift_extractor.match(feats1, feats2, ratio=0.8)
print(len(feats1), len(feats2), len(matches))
```

If import fails with a missing `.so`, the host stack/loader path is incomplete — fix the driver/runtime, not pip.

The wheel includes `sift_extractor/licenses/` (`Apache-2.0.txt`, `MIT.txt`,
`third_party_programs.txt`) for notices covering the packaged native extension
(including SYCL/CudaSift-derived code).
