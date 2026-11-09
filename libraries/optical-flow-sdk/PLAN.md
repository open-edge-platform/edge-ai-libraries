# Intel Optical Flow SDK — Plan

Status: **in progress**. Decisions locked 2026-11-09. CPU classical paths,
OpenCV synthetic parity harness, monorepo content grep, and root README
listing landed on branch `optical-flow-plan` (2026-11-09). **OpenCL DIS
kernels + Core Ultra Series 2 iGPU lab baselines landed 2026-11-09** (host
`labrat`, Core Ultra 7 255H / Arc Graphics). SYCL still blocked (no oneAPI
/`icpx` on that host). Sintel/KITTI datasets and Arc B580 discrete remain
open. Research base written 2026-11-08; SIFT scaffolding
(`libraries/sift-extractor`, PR #3646, ITEP-93043) is reuse-only and does
not define product identity.

### Implementation status (2026-11-09)

| Area | Status |
|------|--------|
| Tree / CMake / CI (`optical-flow-sdk.yml`) | Done (CPU CI on GitHub runners) |
| C++ API: `OpticalFlow`, presets, cost, `calcBoth` | Done |
| `Algorithm::{Dis,Farneback}` | Done (CPU); DIS also on OpenCL |
| CPU DIS-lite dense flow | Done (synthetic-shift tests pass) |
| CPU Farneback-class dense flow | Done |
| CPU `SparsePyrLK` (+ Python) | Done |
| Python `OpticalFlow` bindings | Done |
| Optional OpenCV `Mat` adapter + CPU compare tool | Done (`compare_opencv_dis`: DIS/Farneback/PyrLK) |
| OpenCV CPU synthetic parity (DIS / Farneback / PyrLK) | Done (soft `--strict` GT-EPE gates) |
| EPE / Middlebury `.flo` I/O (`metrics.hpp`, `eval_flow_epe`) | Done |
| Samples: calc / stabilise / track points | Done |
| Determinism + `calcBoth` consistency tests | Done |
| Real OpenCL DIS kernels | **Done** (device pyramid + patch IS + densify; synthetic EPE ≈0) |
| Real SYCL DIS kernels | **Blocked** (no `icpx`/oneAPI on lab host; still CPU fallback) |
| OpenCV DIS parity gate on Sintel/KITTI | **Lab** (needs datasets + honest DIS parity) |
| ≥10× vs OpenCV CPU DIS-Fast | **Not met yet** on Core Ultra 7 255H iGPU (see §11.5) |
| Absolute FPS (≥60@720p / ≥30@1080p) | **Met** on Core Ultra 7 255H Arc Graphics OpenCL Fast |
| SEA-RAFT OpenVINO accuracy tier | **Not started** (P2) |
| Root README under Computer Vision Primitives | Done |
| `gvaopticalflow` DL Streamer element | **Not started** (P3) |
| IPU DVS path | Deferred (out of scope) |

## 1. Decision

Build an **Intel Optical Flow SDK** that closes Nvidia’s Optical Flow SDK
(NVOFA) moat on Intel edge hardware: SYCL + OpenCL algorithm equivalence
and GPU software optimization, with first-class C++ and Python APIs,
NVOFA-shaped presets/cost/`calcBoth`, order-of-magnitude iGPU speedup vs
OpenCV CPU, and fair comparative reporting vs Nvidia’s GPU product.

Do not attempt a hardware-offload port of NVOFA: Intel has no public
fixed-function optical-flow equivalent for general video (see §3–§4).
Do not follow `*-extractor` naming; this product is an SDK.

Home (locked; present in-tree):

```
open-edge-platform/edge-ai-libraries
└── libraries/optical-flow-sdk/
    ├── PLAN.md
    ├── README.md
    ├── CMakeLists.txt
    ├── include/optical_flow_sdk/   # OpticalFlow, Farneback, SparsePyrLK, metrics
    ├── src/cpu/                    # DIS-lite, Farneback, PyrLK
    ├── src/opencl/                 # real DIS kernels (lab-validated)
    ├── src/sycl/                   # wired; CPU fallback until icpx available
    ├── tests/ · benchmarks/ · samples/ · python/ · docs/
    │     # compare_opencv_dis + test_opencv_cpu_parity + opencl synthetic
└── .github/workflows/optical-flow-sdk.yml   # CPU + OpenCV adapter; --strict compare
```

CMake option prefix: `OPTICALFLOW_`. Default host build: CPU ON, SYCL/OpenCL
OFF until `icpx` / OpenCL ICD available.

Why this repo, and not the alternatives:

- **edge-ai-libraries, "Computer Vision Primitives"** — cross-use-case
  vision building blocks with installable C++ (and Python) APIs on Intel
  CPUs/GPUs. SIFT lives at `libraries/sift-extractor` as a sibling
  primitive; this SDK is a peer product in the same category, not a SIFT
  clone. No optical-flow library existed on main as of 2026-11-08
  (path search: zero matches for "optical", "Farneback", "RAFT",
  "Lucas", or "calcOpticalFlow" — content grep completed 2026-11-09, §11.3).
- **Not `libraries/robotics-ai-libraries/orb-extractor`** — Robotics
  Libraries / ROS packaging; flow consumers are broader than robotics.
- **Not `dlstreamer`** — submodule and pipeline consumer. A
  `gvaopticalflow` element belongs there in Phase 3; the SDK does not.
- **Not `scenescape`** — consumes detections/tracks, not pixel flow.
- **Not OpenVINO as the home, and not a new repo** — classical DIS needs
  no inference runtime for v1; OpenVINO hosts the P2 neural accuracy
  tier. A new repo would lose the SIFT/ORB reviewer pool and CI pattern.

### Out of scope (deferred)

Intel **IPU** DVS optical-flow / motion statistics used for camera
digital video stabilization. Public HAL/bins access is insufficient for
a NVOFA-class claim. Revisit later as a separate effort. No
`Backend::Ipu`, no IPU spike, no IPU gates in this plan.

## 2. Goal and non-goals

Goal: an installable Optical Flow SDK that lets edge-AI users replace a
CPU flow stage (and compete with NVOFA on Intel GPUs) via easy C++ and
Python APIs, running GPU-resident on Intel Arc / Core Ultra iGPU.

Success criteria (v1 unless noted):

- Algorithm equivalence for classical DIS vs OpenCV CPU (parity gate).
- SYCL and OpenCL implementations optimized for Intel iGPU / Arc.
- First-class C++ and Python bindings.
- **≥10× wall** vs OpenCV CPU DIS-Fast at 720p and 1080p on the named
  SKUs; **≥60 FPS wall @720p** and **≥30 FPS wall @1080p** on Arc B580.
- Comparative FPS/quality tables vs NVOFA (labeled hosts).
- **Equivalent or better quality vs NVOFA** is a **P2 accuracy-tier**
  claim (SEA-RAFT OpenVINO), not a v1 DIS claim.

Non-goals for v1:

- Matching NVOFA frame rates as a hard fail gate (comparative reporting
  is required; same-order FPS on Arc vs published Ada Fast is the goal).
- A TensorRT / NVOFA hardware clone, a new inference runtime, or a
  DALI-style training loader.
- Neural flow (RAFT / SEA-RAFT) as the first implementation — that is
  the P2 accuracy tier under the same SDK API.
- IPU DVS stats productization (deferred; see §1).
- Multi-GPU collectives, a second CUDA Lucas-Kanade implementation
  (Flipster already exists, MIT — reuse harness patterns, don’t
  duplicate), or a duplicate ORB extractor.

## 3. The Nvidia reference — Optical Flow SDK (NVOFA)

Source: Nvidia docs, Optical Flow SDK 5.0, February 2023, last updated
27 Feb 2023. No 5.1 / 6.0 release was found as of 2026-11-09
(P0 re-verified 2026-11-09 via `proxy-dmz.intel.com` fetch of Nvidia docs:
still SDK 5.0 / Feb 2023; no 5.1/6.0/Blackwell docs found).

- Hardware: Turing-generation GPUs and newer contain a dedicated
  optical-flow accelerator (NVOFA), independent of CUDA cores, supported
  on all Turing GPUs except TU117 and above.
- What SDK 5.0 exposes: CUDA, DirectX 11/12, and Vulkan interfaces;
  forward and backward flow in a single `NvOFExecute` call
  (`predDirection = BOTH`); global flow; external hints (highest
  importance) and temporal hints (on by default, disable only on scene
  cuts); output cost (8-bit recommended; higher cost = less accurate);
  presets SLOW / MEDIUM / FAST; ROI and 2×2 / 1×1 grids on Ampere/Ada
  only; max resolution 4096×4096 (Turing) / 8192×8192 (Ampere/Ada).
  Stereo-disparity mode is deprecated — use the X component of flow.
- Output format: block-based (4×4, 2×2, or 1×1 pixel grids), S10.5
  fixed point (16-bit signed, 5 fractional bits; `CV_16SC2` in the
  OpenCV wrapper, `upSampler()` to dense), quarter-pixel precision only,
  8-bit YUV/RGB input only, no padding on input frames, APIs are not
  thread-safe.
- Published reference performance, KITTI 2015 at 1080p, YUV 4:2:0,
  SDK 5.0 (Nvidia Application Note, Table 3):

  | Grid | Preset | Fl-all NOC, Ada | FPS @1080p, Ada |
  |------|--------|-----------------|-----------------|
  | 4×4  | SLOW   | 17.26%          | 536             |
  | 4×4  | MEDIUM | 19.11%          | 1000            |
  | 4×4  | FAST   | 23.48%          | 1296            |

  Fast, mediocre accuracy. Treat these numbers as a reference ceiling,
  labelled "published, different host" — never plot them on the same
  bar chart as measured Intel numbers without that label.
- OpenCV wrappers are `cv::cuda::NvidiaOpticalFlow_1_0` /
  `NvidiaOpticalFlow_2_0` only (2.0 merged May 2020). There is no SDK
  5.x wrapper in OpenCV, so an OpenCV-based Nvidia path cannot expose
  5.x features.

## 4. The Intel gap today

Verified as a negative result on 2026-11-09 — this is the point of
the plan:

- **Media engine / Quick Sync (Xe, Arc A/B, Core Ultra iGPU):** decode,
  encode, scaler/format conversion, denoise/deinterlace. Motion
  estimation exists only as an internal encoder stage; it is not an
  exposed flow output. No flow block in the component list.
- **Core Ultra 200S datasheet, Hardware Accelerated Video Processing:**
  no optical flow listed.
- **oneVPL:** scope is decode / encode / VPP only. No optical-flow API.
- **XeSS 3 Multi-Frame Generation** (driver 32.0.101.8425, Jan 2026):
  a software optical-flow network on XMX AI engines, gaming-only, no
  general-purpose flow API. Do not cite XeSS as an Intel NVOFA
  equivalent.
- **OpenVINO 2026.2 / 2026.3:** no classical optical-flow primitive.
  A neural flow model could be *run* through it — that is the P2
  accuracy tier, not a v1 flow API.
- **Current Intel software path:** OpenCV CPU `calcOpticalFlowFarneback`,
  `calcOpticalFlowPyrLK`, and `cv::DISOpticalFlow`, optionally via
  `UMat` / OpenCL. There is no guarantee any given algorithm has an
  OpenCL path — an OpenCV forum note (2025-07-01) says exactly that.
  The SYCL/OpenCL SDK is justified precisely because the
  Transparent-API path is unreliable for flow.
- **IPU DVS (deferred):** camera-pipeline motion stats for digital
  video stabilization exist in the proprietary imaging stack; they are
  not a public dense OF SDK. Out of scope here.

## 5. Algorithms, in order

### 5.1 DIS — first (Dense Inverse Search, Kroeger et al., ECCV 2016)

- Method: inverse search for patch correspondences (inverse-compositional
  Lucas-Kanade on a patch grid, Hessian pre-computable per patch), dense
  displacement by patch aggregation over multiple scales, variational
  refinement once per scale. OpenCV adds spatial propagation and
  optional initial-flow propagation.
- Why first: dense output; fastest classical dense method with a shipped
  OpenCV baseline; per-patch inverse search is independent, densification
  is a local weighted average, refinement is a stencil sweep — the same
  pyramid + stencil pattern as SIFT scaffolding; tunable operating points
  mirror NVOFA presets; no training data, no model file.
- Published numbers (Kroeger et al., single CPU core, 1024×436):
  300–600 Hz, 42–46 Hz including preprocessing; ~6 px EPE at the
  300 Hz operating point; Sintel test Fast EPE 10.13 (s0–10: 2.17,
  s10–40: 5.93, s40+: 59.70). On KITTI: Avg-All 14.4 px, Out-All
  46.21%. DIS is poor on KITTI driving scenes and collapses on very
  large displacements — do not oversell it there. Its strength is
  small-to-medium motion at high frame rate. **DIS alone cannot claim
  NVOFA-equivalent KITTI Fl-all** (literature ~46% vs NVOFA ~17–23%).
- OpenCV API to match for parity: `cv::DISOpticalFlow::create(preset)`,
  presets `ULTRAFAST / FAST / MEDIUM`, `calc(I0, I1, flow)` → `CV_32FC2`,
  plus tunables. SDK public presets are NVOFA-shaped
  `Slow / Medium / Fast` (see §6).

### 5.2 Farneback — second (baseline #2)

- Method: two-frame motion from polynomial expansion (Farneback 2003),
  dense, per-pixel. OpenCV: `calcOpticalFlowFarneback(...)`.
- Why second, not first: slower than DIS and worse at equal speed in
  Kroeger's comparison. On the Flipster host (2-thread Xeon):
  309 ms @720p and 819 ms @1080p CPU, vs DIS-medium 132 ms / 540 ms.
  Keep as the simple, well-understood second implementation / fallback.

### 5.3 Pyramidal Lucas-Kanade — third (sparse first, dense second)

- Method: Lucas & Kanade (1981), Bouguet pyramidal implementation.
  Sparse = only at given feature points; dense = the same 2×2 solve at
  every pixel. OpenCV: `calcOpticalFlowPyrLK`, `buildOpticalFlowPyramid`,
  `cv::SparsePyrLKOpticalFlow`.
- Why third: sparse PyrLK is the smallest kernel in the set, reuses
  pyramid code, and enables feature tracking / stabilisation /
  ORB-SLAM3-style extensions. Dense LK reuses the same solver.
- Reference: Flipster (github.com/lolaitan/Flipster, MIT) — dense
  pyramidal LK in C++17/OpenMP + CUDA 12; reuse benchmark harness
  pattern and kernel decomposition; do not reuse its natural-video
  accuracy claim (tuned for line art).

### 5.4 RAFT / SEA-RAFT — P2 accuracy tier

- RAFT: Sintel test final EPE 2.855, KITTI F1-all 5.10%. SEA-RAFT:
  Spring EPE 0.363, 21 FPS @1080p on an RTX 3090 (smallest model).
- Phase 2 under the same SDK API (Slow / accuracy preset): port
  SEA-RAFT-S to OpenVINO, benchmark on Arc / Core Ultra GPU, and unlock
  the “equivalent or better quality vs NVOFA” claim. Not v1.

## 6. API design

NVOFA-shaped on the outside; OpenCV used for classical parity, not as
the product identity. SIFT-style backend dispatch is scaffolding only.

```cpp
namespace optical_flow_sdk {
enum class Backend    { Auto, Cpu, OpenCL, Sycl };
enum class Preset     { Slow, Medium, Fast };     // NVOFA-shaped dial
enum class Algorithm  { Dis, Farneback };         // dense classical

class OpticalFlow {
public:
  OpticalFlow(Backend backend = Backend::Auto, Preset preset = Preset::Fast,
              Algorithm algorithm = Algorithm::Dis);
  void calc(const ImageView& prev, const ImageView& next, FlowField& flow);
  void calc(const ImageView& prev, const ImageView& next, FlowField& flow,
            CostMap& cost);
  void calcBoth(const ImageView& prev, const ImageView& next,
                FlowField& fwd, FlowField& bwd);
};

// Sparse tracking (SLAM / stabilisation) — separate from dense FlowField.
class SparsePyrLK {
  void calc(const ImageView& prev, const ImageView& next,
            const std::vector<Point2f>& prev_pts,
            std::vector<Point2f>& next_pts,
            std::vector<uint8_t>& status, std::vector<float>& err) const;
};
}
```

- Inputs v1: 8-bit grayscale; NV12 / `VAMemory` / USM residency where
  possible so the GPU path needs no host copy per frame.
- Outputs: dense float flow (`dx, dy`); optional cost/confidence map
  (NVOFA-shaped: higher cost = less accurate). Block-based S10.5 is the
  Nvidia hardware format, not this library’s native output.
- `calcBoth` and cost map are **in v1** (core SDK surface) — landed.
- Core library does not depend on OpenCV; optional OpenCV `cv::Mat`
  adapters (`OPTICALFLOW_BUILD_OPENCV_ADAPTER`) for interop and diagnostics.
- Python module `optical_flow_sdk` exposes `OpticalFlow` and `SparsePyrLK`
  (pybind); NumPy in/out.
- Metrics helpers: banded EPE + Middlebury `.flo` read/write for offline
  harnesses (`eval_flow_epe`).

Dual-tier quality under one API:

- **Latency (v1):** DIS on OpenCL (landed) / SYCL (outstanding) — Fast/Medium
  presets; CPU DIS-lite remains the parity/CI path.
- **Accuracy (P2):** SEA-RAFT-S via OpenVINO — Slow / accuracy preset.

## 7. Kernel plan (SYCL / OpenCL)

**Current state:** OpenCL DIS is device-resident (see `src/opencl/`). SYCL
backend types remain wired but still call the CPU path until `icpx`/oneAPI
is available on the lab host. Further OpenCL/SYCL tuning toward the ≥10×
OpenCV gate is the critical remaining P1 performance work.

Copy scaffolding from `sift-extractor` and the ORB-extractor SYCL
refactor (PR #1785) — device selection, USM vs buffers, kernel launch —
do not invent it per algorithm. Product naming and success criteria
remain SDK/NVOFA, not SIFT.

- Pyramid build: shared pattern with SIFT/ORB — grayscale pyramid,
  gradients, per-scale workspace.
- DIS: per-patch inverse search (one work-item per patch, Hessian
  pre-computed); densification as local weighted average; variational
  refinement as a stencil sweep once per scale.
- Farneback: polynomial-expansion stage, then per-pixel displacement
  solve.
- PyrLK: per-point 2×2 solve (sparse); dense variant reuses the same
  solver with a different launch configuration. Flipster decomposition
  is the reference: fused warp + residual + normal-equations →
  separable box filter → per-pixel damped 2×2 solve.
- Warp / remap: needed for forward-backward consistency and FRUC.
- Primary optimisation target: Intel Arc. UHD Graphics 770 is for
  correctness checks, not tuning.

## 8. Benchmark protocol and gates

Principle: accuracy at native benchmark resolutions, speed at edge
resolutions, classical correctness = parity with OpenCV CPU on the same
parameters. Moat success = order-of-magnitude GPU vs CPU plus fair
Nvidia comparative reporting. NVOFA quality parity is a P2 gate.

### Datasets

| Dataset | Resolution | Split | Metric |
|---------|------------|-------|--------|
| MPI Sintel | 1024×436 | Train Clean + Final | EPE all / s0–10 / s10–40 / s40+ |
| KITTI Flow 2015 | 1242×375 | Train 200 pairs | Fl-all / Fl-bg / Fl-fg, EPE |
| Spring | 1920×1080 | Train | EPE, 1px, Fl, WAUC; high-detail split separately |
| Middlebury | ~640×480 | 8 sequences incl. RubberWhale | EPE (sanity check) |
| Synthetic shift | 480p / 720p / 1080p / 4K | Flipster textured pair, known shift 12.5 × −7.25 px | EPE (must be ≈0.045 px class) |

Timing runs at 1280×720 and 1920×1080 on the same content, plus 480p
for the Flipster-comparable row. Never report a single "FPS" without
its resolution, preset, and host.

### Metrics (every run)

- Accuracy: EPE (mean, and by displacement band), Fl-all/Fl-bg/Fl-fg
  on KITTI, 1px outlier rate on Spring, forward–backward consistency
  error where both directions are computed.
- Speed: ms/frame (median, p95, min) and derived FPS; separate kernel
  time from wall time including host↔device copies; warm-up ≥20 frames,
  timed ≥100 frames, 3 repetitions.
- Resource: peak device memory, CPU utilisation during GPU runs, power
  if measurable.

### Baselines (same host, same data, same day)

1. OpenCV CPU `DISOpticalFlow`, all three presets — the correctness baseline.
2. OpenCV CPU `calcOpticalFlowFarneback`, default tutorial parameters
   `(0.5, 3, 15, 3, 5, 1.2, 0)` and one tuned set.
3. OpenCV CPU `calcOpticalFlowPyrLK` (sparse, 500 Shi-Tomasi points) —
   tracking accuracy, not dense EPE.
4. Nvidia reference numbers, literature only if no Nvidia host is
   available: NVOFA §3 and SEA-RAFT-S 21 FPS @1080p / Spring EPE 0.363.
   Label "published, different host".
5. Flipster CUDA LK, if a CUDA host is available: 16.6 ms kernel /
   33.4 ms wall @1080p, T4.

### Gates (ratified)

Named benchmark SKUs (locked): **Core Ultra Series 2 iGPU** and
**Arc B580**.

- **Parity gate (must pass before any speed claim):** SYCL/OpenCL DIS vs
  OpenCV CPU DIS, same preset/parameters, Sintel train Clean+Final and
  KITTI train 200: mean EPE difference ≤ 0.05 px absolute or ≤ 2%
  relative, whichever is larger, on each displacement band; Fl-all
  difference ≤ 0.5 percentage points on KITTI; synthetic-shift EPE
  ≤ 0.10 px.
- **Regression gate:** no preset may be >5% worse (EPE) than its OpenCV
  counterpart on Sintel Final.
- **Determinism gate:** same input → same output (bit-identical or
  ≤1 ULP) across 5 runs on the same device; CPU-fallback and GPU paths
  must agree within the parity gate.
- **Speed gate (v1 success):** DIS Fast on Core Ultra Series 2 iGPU
  **and** Arc B580: **≥10× wall** vs OpenCV CPU DIS-Fast at 720p and
  1080p (host↔device included); **≥60 FPS wall @720p** and **≥30 FPS
  wall @1080p** on Arc B580. If the 10× gate fails, the deliverable is
  still the parity-validated SDK + the measurement — no inflated claim.
- **Nvidia comparative (reporting gate):** same resolution/preset-class
  table vs NVOFA published Ada (and measured Nvidia host if available),
  always labeled host/driver/SDK. Goal: same order of FPS at Fast on
  Arc B580 vs published Ada Fast, with quality delta reported. Not a
  hard v1 fail.
- **Quality gate (P2 accuracy tier):** SEA-RAFT OpenVINO achieves
  ≤ NVOFA Medium Fl-all on KITTI train (or better) at a measured
  Arc/Core Ultra FPS — unlocks “equivalent or better quality vs NVOFA”.
- **Reporting gate:** every speed number accompanied by host (CPU model,
  GPU model, driver, oneAPI version, OpenCV version + build flags),
  resolution, preset/parameters, warm-up/repetitions, and kernel-vs-wall
  split. Numbers without this context are not accepted into the report.

SIFT’s benchmark discipline applies to measurement hygiene only: include
conversion / upload / extraction and owned host outputs; exclude one-time
context/workspace setup and decode/resize outside the timed path;
prefer fresh processes, counterbalanced backend order, and enough
samples for median/p95.

## 9. Integration

- **DL Streamer:** `gvaopticalflow` in P3 (name locked; no such element
  in 2026.0/2026.2 element lists). Example:
  `decodebin3 ! gvaopticalflow preset=fast device=GPU`, emitting dense
  flow as metadata consumable by `gvatrack`, `gvamotiondetect`, and
  `gvawatermark`. Existing `gvamotiondetect` is frame-differencing /
  block motion on NV12 — template, not a substitute. Metadata contract
  defined in P3 against those consumers.
- **Scenescape:** flow is upstream, not inside SceneScape.
- **ORB-SLAM3 / SIFT:** sparse PyrLK as the SLAM-facing deliverable in
  P2; dense flow as a motion prior for matching is a follow-on
  experiment, not assumed in v1.
- **Use cases:** motion ROI / smart motion detection; object tracking;
  video stabilisation; frame interpolation / FRUC; VSLAM / robotics;
  video-analytics pre-filter.

## 10. Roadmap

- **P0 — Spike:** **done on Core Ultra Series 2 iGPU** (§11.5). Content
  grep done (§11.3). OpenCV CPU + `UMat` baselines + driver pin recorded
  on Core Ultra 7 255H. Arc B580 discrete and Nvidia SDK freshness still
  open. Exit for Series 2 iGPU: baseline numbers + named stack — met.
- **P1 — SDK v1:** **partially landed.** Tree, CPU DIS/Farneback,
  `SparsePyrLK`, cost/`calcBoth`, C++ + Python, OpenCV adapter, EPE/flo
  harness, OpenCV CPU synthetic parity, CPU CI, samples, **OpenCL DIS
  kernels** — done. **Still open for P1 exit:** SYCL DIS kernels
  (needs oneAPI), Sintel/KITTI parity vs OpenCV DIS, ≥10× vs OpenCV
  CPU DIS-Fast (absolute FPS gates already met on Series 2 iGPU).
- **P2 — Accuracy tier:** SEA-RAFT-S OpenVINO under Slow; classical
  Farneback/PyrLK GPU ports + OpenCV parity. (CPU Farneback/PyrLK already
  present as classical scaffolding.) Exit: neural quality gate measured.
- **P3 — Pipeline integration:** `gvaopticalflow`; richer samples. Root
  README Computer Vision Primitives listing — done. Exit: DL Streamer
  pipeline GPU-resident with no host copy per frame where the path allows
  it.
- **P4 — Harden comparative story:** measured Nvidia host numbers if
  available; FRUC/warp demos; further preset tuning; SEA-RAFT Intel-GPU
  feasibility notes if still open.

Build / CI:

```
# CPU-only (current CI / this workstation)
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_CPU=ON -DOPTICALFLOW_ENABLE_SYCL=OFF \
  -DOPTICALFLOW_ENABLE_OPENCL=OFF -DOPTICALFLOW_BUILD_TESTS=ON \
  -DOPTICALFLOW_BUILD_OPENCV_ADAPTER=ON -DOPTICALFLOW_BUILD_PYTHON=ON

# Lab OpenCL (Intel GPU ICD; headers may need OPTICALFLOW_OPENCL_INCLUDE_DIR)
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_CPU=ON -DOPTICALFLOW_ENABLE_OPENCL=ON \
  -DOPTICALFLOW_ENABLE_SYCL=OFF -DOPTICALFLOW_BUILD_TESTS=ON

# Lab SYCL+OpenCL (requires icpx / oneAPI — not yet on Core Ultra 7 255H lab host)
cmake -S . -B build -DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_SYCL=ON -DOPTICALFLOW_ENABLE_OPENCL=ON \
  -DOPTICALFLOW_ENABLE_CPU=ON -DOPTICALFLOW_BUILD_TESTS=ON
```

Scoped GitHub Actions builds/tests the **CPU** path (installs OpenCV for
adapter diagnostics and soft synthetic parity: `test_opencv_cpu_parity`
plus `compare_opencv_dis --strict`). No Intel GPU runners; OpenCL/SYCL
CTest, Arc timing, and Sintel/KITTI OpenCV parity are lab gates.
Apache-2.0, DCO sign-off, fork from `main`, PRs as the contribution path
— same as CONTRIBUTING.md.

## 11. Decisions (locked) and verification backlog

### 11.1 Locked decisions

| Decision | Resolution |
|----------|------------|
| Product name / home | `libraries/optical-flow-sdk/`; include `optical_flow_sdk/`; CMake `OPTICALFLOW_`; workflow `optical-flow-sdk.yml` |
| Product identity | Intel Optical Flow SDK (NVOFA-competitive), not `*-extractor` |
| C++ facade | `OpticalFlow`; `Backend { Auto, Cpu, OpenCL, Sycl }`; `Preset { Slow, Medium, Fast }`; `Algorithm { Dis, Farneback }` |
| Sparse tracking | `SparsePyrLK` (C++ + Python) |
| Python | First-class in v1 — landed |
| `calcBoth` + cost | In v1 — landed |
| IPU / DVS | Deferred / out of scope for this plan |
| Benchmark SKUs | Core Ultra Series 2 iGPU + Arc B580 |
| §8 gates | Ratified as written (parity, regression, determinism, ≥10× speed, Nvidia reporting, P2 quality, reporting) |
| DL Streamer element | `gvaopticalflow` in P3 |
| OpenCV role | Optional adapters + classical correctness baseline; core has no OpenCV dependency |
| Algo order | DIS (P1 device kernels) → Farneback/PyrLK GPU + SEA-RAFT OpenVINO (P2); CPU classical already present |
| SIFT/ORB | Scaffolding reuse only |

### 11.2 Verification backlog (not product forks)

| Item | When | Notes |
|------|------|-------|
| In-repo content grep for existing flow code | P0 | **Done 2026-11-09** — see §11.3 |
| OpenCV `UMat`/OpenCL path for DIS / Farneback / PyrLK on target SKU | P0 | **Done 2026-11-09** on Core Ultra 7 255H — see §11.5 |
| Named driver + oneAPI versions on benchmark hosts | P0 | **Driver pinned** (§11.5); oneAPI **absent** on lab host |
| OpenCV CPU baselines on Core Ultra Series 2 + Arc B580 | P0 | Series 2 iGPU **done**; Arc B580 discrete still open |
| Nvidia SDK beyond 5.0 / Blackwell support | P0 | **Done 2026-11-09** via `proxy-dmz.intel.com:911/912` — app note / prog guide / release notes / index / developer page all still **SDK 5.0** (last updated **Feb 27, 2023**); no 5.1/6.0/Blackwell docs; Table 3 Ada 4×4 Fl-all/FPS unchanged (17.26/536, 19.11/1000, 23.48/1296). Artifact: `.nvofa-summary.json` (gitignored) |
| Replace OpenCL CPU fallback with real DIS kernels | P1 | **Done 2026-11-09** |
| Replace SYCL CPU fallback with real DIS kernels | P1 | Blocked without oneAPI/`icpx` |
| OpenCV CPU synthetic GT-EPE (DIS / Farneback / PyrLK) | P1 | **Done 2026-11-09** — soft CI gates; not OpenCV numerical identity |
| Sintel/KITTI parity vs OpenCV DIS | P1 | Synthetic harness exists; datasets + lab run outstanding |
| SEA-RAFT / RAFT on Intel GPU via OpenVINO | P2 / P4 | No published Intel-GPU benchmark found; feasibility unverified |
| `gvaopticalflow` metadata contract vs `gvatrack` / `gvamotiondetect` | P3 | Define when element lands |
| IPU DVS productization | Deferred | Separate future plan |

### 11.3 Content grep result (2026-11-09)

Searched the monorepo (excluding `libraries/optical-flow-sdk/` and
build/`pcl` patch blobs) for
`calcOpticalFlow|DISOpticalFlow|Farneback|PyrLK|optical.?flow|NVOFA|Lucas.?Kanade|SEA-?RAFT|\bRAFT\b`
and related dense/sparse flow tokens.

| Hit | Classification |
|-----|----------------|
| `libraries/video-chunking-utils/.../pelt_chunk.py` uses `cv2.calcOpticalFlowFarneback` for a motion-difference feature | **Consumer** of OpenCV Farneback — not a competing SDK; future optional adopter of this library |
| Chinese prompt strings mentioning “Raft” (consensus) under `microservices/inference-router` | False positive |
| Binary noise inside `libraries/robotics-ai-libraries/pcl/patches/...` | False positive |

**Conclusion:** no prior Optical Flow SDK / NVOFA-class product, and no
in-tree classical DIS/Farneback/PyrLK library besides this tree and the
one OpenCV Farneback call site above. Path search from 2026-11-08 stands.
`video-chunking-utils` is a future optional adopter, not a blocker.

### 11.4 Remaining without lab hardware

Useful on a CPU-only host (not moat-closing): OpenMP/SIMD on DIS-lite,
NV12 plane helpers, ASAN/UBSAN in CI, SEA-RAFT OpenVINO stub under Slow,
richer samples/docs. **Still blocked without more HW / datasets / oneAPI:**
SYCL DIS kernels, Arc B580 discrete ≥10× gates, honest Sintel/KITTI
OpenCV DIS parity, `gvaopticalflow` GPU-resident path.

### 11.5 Lab host results (2026-11-09) — Core Ultra Series 2 iGPU

Host multiplexed as SSH ControlMaster `arc` (`labrat@10.91.82.130`).

| Field | Value |
|-------|-------|
| CPU | Intel Core Ultra 7 255H (16 threads) |
| GPU | Arrow Lake-P Intel Arc Graphics (PCI `8086:7d51`) |
| Kernel | Linux 6.17.0-14-generic (`xe` + `i915` modules present) |
| OpenCL | Intel OpenCL Graphics / Arc Graphics, OpenCL 3.0 NEO, driver **26.14.37833.4**, IGC 2.32.7, 128 CUs |
| Level Zero | 1.8.1 + `libze-intel-gpu` 26.14.37833.4 |
| oneAPI / `icpx` | **Not installed** (`/opt/intel/oneapi` absent) — SYCL path blocked |
| OpenCV | 4.14.0-pre at `~/opencv/build_host`, `WITH_OPENCL=ON`, `haveOpenCL=1` |

**OpenCV CPU vs UMat (synthetic textured shift, wall ms/frame):**

| Res | Algo | CPU ms | UMat ms | Note |
|-----|------|--------|---------|------|
| 720p | DIS Fast | 8.88 | 17.37 | UMat **slower** than CPU |
| 1080p | DIS Fast | 16.33 | 29.80 | UMat **slower** than CPU |
| 720p | Farneback | 101.6 | 22.57 | UMat ~4.5× faster |
| 1080p | Farneback | 253.2 | 46.52 | UMat ~5.4× faster |

Conclusion: OpenCV Transparent-API DIS is **not** a usable GPU path on this
SKU (matches plan §4). Farneback UMat does accelerate. Custom OpenCL DIS
is justified.

**SDK OpenCL DIS Fast (persistent workspace, wall incl. H↔D):**

| Res | OpenCL ms | OpenCL FPS | vs SDK CPU | vs OpenCV CPU DIS-Fast |
|-----|-----------|------------|------------|-------------------------|
| 720p | 11.71 | **85.4** | ~5.1× | 0.76× (OpenCV still faster) |
| 1080p | 26.64 | **37.5** | ~5.2× | 0.61× (OpenCV still faster) |

Synthetic-shift OpenCL EPE ≈ 8e-6 (parity with CPU DIS-lite). Absolute FPS
thresholds from the Arc B580 gate (≥60@720p, ≥30@1080p) are already met on
this Series 2 iGPU. The **≥10× vs OpenCV CPU DIS-Fast** moat gate is **not**
met — further kernel tuning (and/or SYCL) required; do not claim 10×.

## 12. Sources

- Nvidia NVOFA Application Note, SDK 5.0:
  https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvofa-application-note/index.html
- Nvidia NVOFA Programming Guide, SDK 5.0:
  https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvofa-programming-guide/index.html
- OpenCV `cv::DISOpticalFlow`:
  https://docs.opencv.org/4.13.0/de/d4f/classcv_1_1DISOpticalFlow.html
- OpenCV Farneback / PyrLK:
  https://docs.opencv.org/3.4.16/dc/d6b/group__video__track.html
- OpenCV CUDA optical flow:
  https://docs.opencv.org/4.5.4/d5/d26/classcv_1_1cuda_1_1NvidiaHWOpticalFlow.html
- DIS paper (Kroeger et al., ECCV 2016): https://ar5iv.labs.arxiv.org/html/1603.03590
- Flipster (CUDA pyramidal LK benchmark, MIT):
  https://github.com/lolaitan/Flipster
- Intel Media Engine Hardware (no flow block):
  https://www.intel.com/content/www/us/en/docs/oneapi/optimization-guide-gpu/2025-2/media-engine-hardware.html
- DL Streamer elements:
  https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/elements/elements.html
- Full research base (2026-11-09, with per-source notes):
  `~/workspace/research_notes/optical-flow-intel-plan-20261109-0346/report.md`
  in the author's workspace; the ranked Nvidia-moat list this plan
  came from is at
  `~/workspace/research_notes/nvidia-moat-low-hanging-intel-20261108-0753/report.md`.
