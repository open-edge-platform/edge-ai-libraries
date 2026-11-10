<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Optical Flow SDK — Benchmarks

Lab quality/speed numbers, protocol/gates, and how to reproduce them.
Product Fast bar: **≥6×** vs OpenCV CPU DIS-Fast @720p on the OpenCL
**device-resident** path; KITTI Fl-all vs **measured NVOFA** (not OpenCV
drop-in). SEA-RAFT setup: [`../docs/sea_raft.md`](../docs/sea_raft.md).

Optional local JSON under `results/` is gitignored — refresh the tables
here when numbers change.

---

## 1. Lab host (labrat)

| Field | Value |
|-------|-------|
| Host | `labrat@10.91.82.130` (SSH ControlMaster `arc`) |
| CPU | Intel Core Ultra 7 255H (16 threads) |
| GPU | Arrow Lake-P Intel Arc Graphics (iGPU), PCI `8086:7d51` |
| OpenCL | Intel NEO OpenCL 3.0, driver **26.14.37833.4**, 128 CUs |
| Level Zero | 1.8.1 + `libze-intel-gpu` 26.14.37833.4 |
| SYCL | User-local oneAPI `~/intel/oneapi` (compiler 2025.3); `ONEAPI_DEVICE_SELECTOR=opencl:gpu` |
| OpenCV reference | 4.14.0-pre host build (`WITH_OPENCL=ON`, `haveOpenCL=1`) |
| Datasets | `~/datasets/optical-flow` (KITTI 2015 + MPI Sintel) |

Nvidia comparative rows use a **separate** host (`gklab-233-162`, RTX 5060)
— do not bar-chart as same-silicon.

### Why custom OpenCL DIS (not OpenCV UMat)

| Res | Algo | CPU ms | UMat ms | Note |
|-----|------|--------|---------|------|
| 720p | DIS Fast | 8.88 | 17.37 | UMat **slower** than CPU |
| 1080p | DIS Fast | 16.33 | 29.80 | UMat **slower** than CPU |
| 720p | Farneback | 101.6 | 22.57 | UMat ~4.5× faster |
| 1080p | Farneback | 253.2 | 46.52 | UMat ~5.4× faster |

OpenCV Transparent-API DIS is not a usable GPU path on this SKU. Farneback
UMat does accelerate. Custom OpenCL DIS is justified.

---

## 2. Quality (KITTI Fl-all)

Lower Fl-all is better. Classical SDK DIS is **DIS-lite** (no OpenCV-style
variational refine on the product Fast path). Product quality bar =
**measured NVOFA**, not pairwise EPE vs OpenCV.

### 2.1 Product Fast vs references

| Implementation | Backend / path | KITTI Fl-all | Notes |
|----------------|----------------|--------------|-------|
| **SDK DIS Fast** (shipped) | OpenCL, cost-weighted densify | **~42.3%** | 50-pair harness; deep pyr + mean-norm/prop@finest; `stride=6`/`gd=8` |
| OpenCV DIS Fast | CPU | ~36% (50-pair) / ~42% (full-200) | Full DIS + red-black variational |
| NVOFA Fast | RTX 5060 (measured) | **34.1%** | Full train 200; native-res grayscale — see §5 |
| SDK quality-max DIS | OpenCL (no ≥6× gate) | ~40% | `stride=4`/`gd=16` @~1.8× — not product Fast |
| + Brox RB-SOR (optional) | OpenCL Fast + var | ~39.7% | `outer=2`/`sor=5`; **~3.2×** — Fast-off |
| **SEA-RAFT-S** | OpenVINO / PyTorch | **2.70%** | P2 quality PASS vs published Ada Medium 19.11% |

Fast path detail: pyramid `coarsest=5`/`finest=2`, atomic-free centers +
cost-weighted densify `w∝a/(c²+1)`, prop+mean-norm **at finest only**.

### 2.2 Classical DIS vs OpenCV (honesty)

SDK DIS is **not** numerically equivalent to OpenCV DIS. §8 pairwise
`≤ max(0.05px, 2%)` and KITTI Fl-all `≤ 0.5pp` classical-equivalence bars
**FAIL** by design. Closest classical GPU path: OpenCL Fast. SEA-RAFT owns
beating NVOFA Fl-all.

**KITTI train 200 (full; pre–costw baseline for OpenCL Fast Fl-all):**

| Backend | Preset | SDK EPE | OpenCV EPE | Pairwise EPE | SDK Fl-all% | OCV Fl-all% |
|---------|--------|---------|------------|--------------|-------------|-------------|
| CPU | Fast | 53.97 | 18.12 | 40.88 | 61.97 | 41.66 |
| CPU | Medium | 76.14 | 16.32 | 65.79 | 53.36 | 33.48 |
| OpenCL | Fast | 35.36 | 18.12 | 20.02 | 74.23 | 41.66 |
| OpenCL | Medium | 53.01 | 16.32 | 42.18 | 53.09 | 33.48 |

Post-retune **product** OpenCL Fast Fl-all on the 50-pair harness is
**~42.3%** (§2.1) — prefer that for shipped Fast.

**Sintel train (69 pairs/pass, stratified; OpenCL Fast is the usable classical config):**

| Backend | Preset | Pass | SDK EPE | OpenCV EPE | Pairwise EPE |
|---------|--------|------|---------|------------|--------------|
| OpenCL | Fast | Clean | 15.38 | 6.91 | 16.68 |
| OpenCL | Fast | Final | 25.23 | 5.57 | 23.28 |
| OpenCL | Medium | Clean | 87.36 | 8.75 | 87.26 |
| OpenCL | Medium | Final | 400.5 | 5.46 | 399.1 |

P2 classical retune improved OpenCL Fast Sintel Clean 15.4→8.8 / Final
25.2→9.2 and fixed Medium Final blow-up; §8 gates remain FAIL.

---

## 3. Performance — CPU vs OpenCL vs SYCL (labrat)

### 3.1 DIS Fast, device-resident (preferred speed path)

Warm kernel / `calc_device` wall. OpenCV CPU DIS-Fast is the × reference
inside `microbench --mode resident`.

| Resolution | Path | Latency | FPS | vs OpenCV CPU DIS-Fast |
|------------|------|---------|-----|-------------------------|
| 1280×720 | **OpenCL** `calc_device` | **~1.93–1.95 ms** | **~510–517** | **~6.1–6.15×** |
| 1920×1080 | **OpenCL** `calc_device` | **~4.15–4.2 ms** | **~238–241** | **~5.7–5.8×** |
| 1280×720 | **SYCL** `calc_device` | **~1.66 ms** | **~600** | **~7×** |
| 1920×1080 | **SYCL** `calc_device` | **~2.13 ms** | **~470** | **~11×** |
| 1280×720 | OpenCV CPU DIS-Fast | ~11.9 ms† | ~84 | 1.0× (reference) |
| 1280×720 | OpenCV UMat DIS-Fast | 17.37 ms | ~58 | **slower** than CPU |

† Implied by OpenCL resident × at ~1.94 ms / ~6.1×. Direct OpenCV wall in
the UMat table was 8.88 ms @720p (different harness); always compare within
the same microbench binary.

**Gates on labrat OpenCL Fast:** ≥60 FPS @720p and ≥30 FPS @1080p **met**;
≥6× @720p resident **met**; @1080p ~5.7×.

**Backend policy:** `Backend::Auto` prefers **OpenCL**, then SYCL, then CPU.
OpenCL is the product ≥6× measurement vehicle. SYCL is a landed catch-up
path (`microbench --backend sycl --mode resident`).

### 3.2 Host `OpticalFlow::calc` (GPU backends)

Includes H↔D. Convenience only — typically **~6–8×** vs OpenCV CPU, not
the speed gate. Prefer facade `Backend` for apps; use `calc_device` only
for zero-copy pipelines
([`../docs/backend-selection.md`](../docs/backend-selection.md)).

### 3.3 SEA-RAFT-S (accuracy tier, not DIS)

| Device | Shape | ms/pair | FPS |
|--------|-------|---------|-----|
| Arc iGPU (OpenVINO) | 384×1248 | ~60–64 | **~15.7–16.6** |
| Arc iGPU (OpenVINO) | 432×960 | ~49.4 | **~20.2** |
| CPU (OpenVINO) | 384×1248 | ~872 | ~1.15 |

Quality **2.70%** Fl-all is independent of this FPS bench.

---

## 4. Quality–speed tradeoffs (OpenCL Fast, labrat)

| Config | Fl-all (50-pair) | × @720p resident | Shipped? |
|--------|------------------|------------------|----------|
| Cost-weighted densify only | **~42.3%** | **~6.1×** | **Yes (product Fast)** |
| + RB-SOR `outer=1`/`sor=1` | ~41.6–42.1% | ~4.8–5.0× | No |
| + RB-SOR `outer=2`/`sor=5` | ~39.7% | ~3.2× | Optional / Fast-off |
| Quality-max (`stride=4`/`gd=16`) | ~40% | ~1.8× | No |

Kept under ≥6×: costw `1/(c²+1)` densify (−2.2pp Fl-all, speed held).
Rejected under speed or quality: mid-prop / mean-all / dense median;
softmin densify; sparse patch median; `prop=3`; mean@finest+1.

---

## 5. Nvidia NVOFA comparative (separate host)

Host: Core Ultra 7 265K + **RTX 5060**, driver 595.99, CUDA 13.1, 4×4 grid.

| Preset | FPS @720p | FPS @1080p | KITTI train Fl-all (200) | vs published Ada Fl-all @1080p |
|--------|-----------|------------|---------------------------|--------------------------------|
| Slow | 1634 | 684 | 28.36% | 17.26% |
| Medium | 2669 | 1350 | 30.18% | 19.11% |
| Fast | 3627 | 1881 | **34.09%** | 23.48% |

FPS is device-resident `nvOFExecute` wall (synthetic pair). KITTI Fl-all is
native-resolution grayscale + nearest S10.5 upsample (not Ada’s 1080p YUV
methodology). Use measured RTX 5060 numbers when comparing to Intel lab
Fl-all.

---

## 6. Protocol and gates

Named SKU: **Core Ultra Series 2 iGPU** (labrat). Accuracy at native
dataset resolutions; speed at 720p/1080p. Never report FPS without
resolution, preset, and host.

| Dataset | Role |
|---------|------|
| KITTI Flow 2015 train | Primary Fl-all / EPE vs NVOFA |
| MPI Sintel train Clean/Final | Honesty EPE vs OpenCV DIS |
| Synthetic textured shift | Smoke EPE / microbench |

**Gates:**

- **Speed (product):** OpenCL `calc_device` DIS Fast ≥**6×** vs OpenCV CPU
  DIS-Fast @720p/1080p; ≥60 FPS @720p; ≥30 FPS @1080p.
- **Quality (classical):** report KITTI Fl-all vs **measured NVOFA** (not
  OpenCV drop-in). Target: within ~5–10pp of NVOFA Fast (~34% RTX 5060).
- **OpenCV DIS parity:** diagnostic only — DIS-lite vs full OpenCV DIS is
  expected to **FAIL** old ≤0.05px / ≤0.5pp bars (§2.2).
- **P2 accuracy:** SEA-RAFT-S ≤ NVOFA Medium Fl-all on KITTI train
  (`docs/sea_raft.md`) — unlocks “better than NVOFA” claim.
- **Reporting:** every speed number needs host/driver/OpenCV/oneAPI,
  resolution, preset, warm-up/reps, kernel-vs-wall split.

## 7. Harnesses

| Binary | Role |
|--------|------|
| `microbench` | Unified CPU/OpenCL/SYCL host + resident timings (`--backend` / `--mode`) |
| `microbench_nvofa` | Nvidia host FPS + optional KITTI Fl-all (CUDA; not in CMake) |
| `eval_flow_epe` | Banded EPE; synthetic or `--gt/--pred` `.flo` |
| `compare_opencv_dis` | Synthetic OpenCV parity (DIS/Farneback/PyrLK); `--strict` for CI |
| `parity_opencv_datasets` | Sintel + KITTI OpenCV DIS disparity (adapter ON) |

---

## 8. How to reproduce (labrat)

```bash
./scripts/fetch_datasets.sh ~/datasets/optical-flow

# OpenCL resident speed (product gate)
cmake --build build-opencl-parity -j$(nproc) --target microbench
./build-opencl-parity/microbench --backend opencl --mode resident

# OpenCL KITTI Fl-all (product Fast)
./build-opencl-parity/parity_opencv_datasets \
  --kitti ~/datasets/optical-flow --backend opencl --preset fast --max-pairs 50

# Full honesty tables (KITTI 200 / Sintel 69)
./build-opencl-parity/parity_opencv_datasets \
  --kitti ~/datasets/optical-flow --backend opencl --preset fast
./build-opencl-parity/parity_opencv_datasets \
  --sintel ~/datasets/optical-flow --backend opencl --preset fast --max-pairs 69

# SYCL resident (oneAPI env)
source ~/intel/oneapi/setvars.sh
export ONEAPI_DEVICE_SELECTOR=opencl:gpu
./build-sycl/microbench --backend sycl --mode resident

# EPE on a pair
./build/eval_flow_epe --gt /data/sintel/flow/xxx.flo --pred /tmp/pred.flo
```

---

## 9. Summary

| Tier | Implementation | Labrat takeaway |
|------|----------------|-----------------|
| **Product classical Fast** | OpenCL DIS + costw densify | **~6.1× @720p**, **~42%** KITTI Fl-all |
| Secondary GPU | SYCL DIS `calc_device` | Competitive / faster resident ms; Auto still prefers OpenCL |
| CPU | OpenCV DIS / SDK CPU | Reference & CI; OpenCV UMat DIS not a GPU win on this SKU |
| Accuracy unlock | SEA-RAFT-S | **2.70%** Fl-all; ~15.7 FPS @384×1248 OV iGPU |

Facade apps should select `Backend` / `Algorithm` / `Preset`
([`../docs/backend-selection.md`](../docs/backend-selection.md)). Packaging:
[`../docs/packaging.md`](../docs/packaging.md).
