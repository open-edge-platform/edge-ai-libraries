# SIFT LZE sample

Thin robotics wrapper around the horizontal `sift_extractor` core.

```bash
sift_feature_extract --image=/path/to/gray_or_bgr.png --images=1 --backend=auto
```

- `--images=N` repeats the same frame N times (same-size multi-camera path).
- Descriptors are **float 128-D (L2)**. Do not use Hamming distance or ORB matchers.
- `SIFT_BACKEND=opencl|sycl|auto` overrides `--backend` when set.
