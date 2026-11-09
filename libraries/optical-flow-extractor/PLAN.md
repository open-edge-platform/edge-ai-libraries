# Optical Flow on Intel Edge Hardware — Plan

Status: plan only. No code in this file. Written 2026-11-08, following the
SIFT OpenCL/SYCL optimisation in `open-edge-platform/edge-ai-libraries`
(`libraries/sift-extractor`, PR #3646, ITEP-93043).

## 1. Decision

Build a software-first SYCL/OpenCL dense optical-flow library for Intel
CPU / iGPU / Arc, starting with DIS (Dense Inverse Search). Do not attempt a
hardware-offload port of Nvidia's Optical Flow SDK: Intel has no public
fixed-function optical-flow equivalent (see §3).

Proposed home, verified 2026-11-08 against the upstream repo tree:

```
open-edge-platform/edge-ai-libraries
└── libraries/optical-flow-extractor/   ← new, this plan
    ├── PLAN.md                          ← this file
    ├── README.md
    ├── CMakeLists.txt
    ├── include/optical_flow_extractor/
    ├── src/                             # SYCL + OpenCL backends
    ├── tests/
    ├── benchmarks/
    ├── samples/
    ├── python/                          # optional wheel, like SIFT
    ├── docs/
    └── .github/workflows/optical-flow-extractor.yml
```

Why this repo, and not the alternatives:

- **edge-ai-libraries, "Computer Vision Primitives"** — the repo README
  defines this category as "cross-use-case vision building blocks that are
  not tied to a single robotics or media pipeline. These components expose
  installable C++ (and optional Python) APIs for feature extraction and
  related primitives on Intel CPUs/GPUs." SIFT lives here at
  `libraries/sift-extractor`. Optical flow is the same kind of building
  block. No optical-flow library exists in the repo today: a file-path
  search of the main branch on 2026-11-08 found zero matches for
  "optical", "Farneback", "RAFT", "Lucas", or "calcOpticalFlow".
- **Not `libraries/robotics-ai-libraries/orb-extractor`** — that is the
  Robotics Libraries category, for robotic perception / SLAM, built with
  ROS Debian packaging, and it has no Python folder and no benchmarks
  folder. Flow's consumers include robotics, but are not limited to it.
- **Not `dlstreamer`** — that is a submodule and a pipeline consumer.
  A new `gvaopticalflow` element belongs there in Phase 3, but the
  library itself does not.
- **Not `scenescape`** — Scenescape consumes detections and tracks, not
  pixel flow. Flow belongs in the pipeline feeding Scenescape.
- **Not OpenVINO, and not a new repo** — classical DIS / Farneback /
  PyrLK need no inference runtime, and a new repo would lose the
  SIFT/ORB reviewer pool, CI pattern, and install conventions.

Naming follows the repo convention (`sift-extractor`, `orb-extractor`).

## 2. Goal and non-goals

Goal: a drop-in, OpenCV-compatible dense-flow library that lets a
DL Streamer / OpenVINO user delete a CPU flow stage from their pipeline
with no model change, and run it GPU-resident on Intel Arc / Core Ultra
iGPU.

Non-goals for v1:

- Matching Nvidia NVOFA frame rates. NVOFA is fixed-function hardware;
  matching it is not a realistic or necessary v1 goal.
- A TensorRT / NVOFA clone, a new inference runtime, or a DALI-style
  training loader.
- A neural flow model (RAFT / SEA-RAFT) as the first implementation.
  That is Phase 2, as an accuracy reference and an OpenVINO port.
- Multi-GPU collectives, a second CUDA Lucas-Kanade implementation
  (Flipster already exists, MIT — port it, don't duplicate it), or a
  duplicate ORB extractor.

## 3. The Nvidia reference — Optical Flow SDK (NVOFA)

Source: Nvidia docs, Optical Flow SDK 5.0, February 2023, last updated
27 Feb 2023. No 5.1 / 6.0 release was found as of 2026-11-09.

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

Verified as a negative result on 2026-11-09 — this is the point of the
plan:

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
  A neural flow model could be *run* through it — that is a model port,
  not a flow API.
- **Current Intel software path:** OpenCV CPU `calcOpticalFlowFarneback`,
  `calcOpticalFlowPyrLK`, and `cv::DISOpticalFlow`, optionally via
  `UMat` / OpenCL. There is no guarantee any given algorithm has an
  OpenCL path — an OpenCV forum note (2025-07-01) says exactly that.
  The SYCL implementation is justified precisely because the
  Transparent-API path is unreliable for flow.

## 5. Algorithms, in order

### 5.1 DIS — first (Dense Inverse Search, Kroeger et al., ECCV 2016)

- Method: inverse search for patch correspondences (inverse-compositional
  Lucas-Kanade on a patch grid, Hessian pre-computable per patch), dense
  displacement by patch aggregation over multiple scales, variational
  refinement once per scale. OpenCV adds spatial propagation and
  optional initial-flow propagation.
- Why first: dense output; fastest classical dense method with a shipped
  OpenCV baseline to be comparable against; per-patch inverse search is
  independent, densification is a local weighted average, refinement is
  a stencil sweep — the same pyramid + stencil pattern as SIFT; tunable
  operating points (patch size/stride, scales, refinement iterations)
  give a speed/accuracy knob per edge SKU, mirroring NVOFA's presets;
  no training data, no model file, no NPU/GPU-model port.
- Published numbers (Kroeger et al., single CPU core, 1024×436):
  300–600 Hz, 42–46 Hz including preprocessing; ~6 px EPE at the
  300 Hz operating point; Sintel test Fast EPE 10.13 (s0–10: 2.17,
  s10–40: 5.93, s40+: 59.70). On KITTI: Avg-All 14.4 px, Out-All
  46.21%. DIS is poor on KITTI driving scenes and collapses on very
  large displacements — do not oversell it there. Its strength is
  small-to-medium motion at high frame rate.
- OpenCV API to match: `cv::DISOpticalFlow::create(preset)`, presets
  `ULTRAFAST / FAST / MEDIUM`, `calc(I0, I1, flow)` → `CV_32FC2`,
  tunables for patch size/stride, finest/coarsest scale, gradient
  descent iterations, mean normalisation, spatial propagation, and
  variational refinement.

### 5.2 Farneback — second (baseline #2)

- Method: two-frame motion from polynomial expansion (Farneback 2003),
  dense, per-pixel. OpenCV: `calcOpticalFlowFarneback(prev, next, flow,
  pyr_scale, levels, winsize, iterations, poly_n, poly_sigma, flags)`.
- Why second, not first: slower than DIS and worse at equal speed in
  Kroeger's comparison. On the Flipster host (2-thread Xeon):
  309 ms @720p and 819 ms @1080p CPU, vs DIS-medium 132 ms / 540 ms.
  Keep as the simple, well-understood second implementation / fallback.

### 5.3 Pyramidal Lucas-Kanade — third (sparse first, dense second)

- Method: Lucas & Kanade (1981), Bouguet pyramidal implementation.
  Sparse = only at given feature points; dense = the same 2×2 solve at
  every pixel. OpenCV: `calcOpticalFlowPyrLK`, `buildOpticalFlowPyramid`,
  `cv::SparsePyrLKOpticalFlow`.
- Why third: sparse PyrLK is the smallest kernel in the set, reuses the
  SIFT/ORB pyramid code directly, and is the immediate enabler for
  feature tracking — ORB-SLAM3 extensions, stabilisation homography
  from tracked corners. Dense LK then reuses the same per-pixel solver.
- Reference: Flipster (github.com/lolaitan/Flipster, MIT, created
  2026-10-02) — dense pyramidal LK in C++17/OpenMP + CUDA 12, with a
  NumPy reference as executable spec, CPU↔CUDA parity tests, and a
  Middlebury harness. Its dense LK does 16.6 ms kernel time @1080p on
  a T4 vs 975 ms C++/OpenMP on the same host. Reuse its benchmark
  harness pattern and kernel decomposition; do not reuse its
  natural-video accuracy claim (tuned for line art; its "EPE 0.045"
  is on a synthetic uniform shift).

### 5.4 RAFT / SEA-RAFT — Phase 2 only

- RAFT: Sintel test final EPE 2.855, KITTI F1-all 5.10%. SEA-RAFT:
  Spring EPE 0.363, 21 FPS @1080p on an RTX 3090 (smallest model).
  Best accuracy, but a 4D correlation volume + recurrent GRU, ~47–110
  ms/frame even on a high-end discrete GPU, needing an ONNX→OpenVINO
  port, quantisation validation, and training-data licensing review.
  Phase 2: port SEA-RAFT-S to OpenVINO, benchmark on Arc / Core Ultra
  GPU, and use it as the accuracy reference for DIS — not as the first
  implementation.

## 6. API design

OpenCV-compatible on the outside, NVOFA-shaped on the inside:

```cpp
// C++ API (v1) — mirrors cv::DISOpticalFlow::calc() and SIFT's
// Extractor dispatch over Backend::OpenCL / Backend::Sycl / Backend::Auto
enum class Backend { OpenCL, Sycl, Auto };
enum class Preset  { Ultrafast, Fast, Medium };   // like DIS + NVOFA SLOW/MEDIUM/FAST

class FlowExtractor {
public:
  FlowExtractor(Backend backend = Backend::Auto, Preset preset = Preset::Fast);
  // flow: CV_32FC2, same size as input; cost/confidence optional, like NVOFA
  void calc(const cv::Mat& prev, const cv::Mat& next, cv::Mat& flow);
  void calc(const cv::Mat& prev, const cv::Mat& next, cv::Mat& flow,
            cv::Mat& cost);                        // forward only, v1
  // forward + backward in one call (NVOFA predDirection=BOTH), v1 if cheap
  void calcBoth(const cv::Mat& prev, const cv::Mat& next,
                cv::Mat& fwd, cv::Mat& bwd);
};
```

- Inputs: 8-bit grayscale (v1); NV12 / `VAMemory` / `UMat` inputs where
  possible, following DL Streamer's VA-API path — do not require a
  host copy for the GPU path.
- Outputs: dense `CV_32FC2` flow, plus an optional cost/confidence map
  (NVOFA-shaped: higher cost = less accurate). Block-based S10.5 is
  the Nvidia hardware format, not this library's output format.
- CPU fallback must be bit-comparable to OpenCV within the parity gate
  in §8. Core library does not depend on OpenCV; optional OpenCV
  `cv::Mat` adapters, like SIFT ("not OpenCV features2d SIFT" — here,
  not OpenCV `video` flow).
- Python bindings (optional, SIFT-style pybind wheel) — confirm whether
  v1 needs them; SIFT has them, and DL Streamer Python is a likely user.

## 7. Kernel plan (SYCL, reusing the SIFT pattern)

Copy the scaffolding from the sibling `sift-extractor` and from the
ORB-extractor SYCL refactor (PR #1785 in the same repo) — device
selection, USM vs buffers, kernel launch — do not invent it per
algorithm.

- Pyramid build: shared with SIFT/ORB — grayscale pyramid, gradients,
  per-scale workspace. One pyramid codebase, three consumers
  (SIFT, ORB, flow).
- DIS: per-patch inverse search (independent patches → one work-item
  per patch, Hessian pre-computed); densification as a local weighted
  average; variational refinement as a stencil sweep, once per scale.
- Farneback: polynomial-expansion stage, then per-pixel displacement
  solve — parallelisable, but less obviously than DIS's patch grid.
- PyrLK: per-point 2×2 solve (sparse); dense variant reuses the same
  solver with a different launch configuration. Flipster's decomposition
  is the reference: fused warp + residual + normal-equations →
  separable box filter → per-pixel damped 2×2 solve; shared-memory row
  tile + coalesced running-sum vertical pass.
- Warp / remap: reuse the NPP-style warp primitive from the
  fused-preprocessing work (ranked #1–#2 in the Nvidia-moat list) —
  flow needs warp for forward-backward consistency checks and for
  frame interpolation / FRUC.
- Primary optimisation target: Intel Arc. UHD Graphics 770 is for
  correctness checks, not tuning — same rule as SIFT.

## 8. Benchmark protocol and gates

Principle: accuracy at native benchmark resolutions, speed at edge
resolutions, correctness defined as parity with OpenCV CPU on the same
parameters — not as beating RAFT.

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
  time from wall time including host↔device copies (Flipster shows wall
  is ~2× kernel at 1080p on PCIe — report both or the number is
  meaningless); warm-up ≥20 frames, timed ≥100 frames, 3 repetitions.
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

### Gates (proposed — to be ratified by the plan owner)

- **Parity gate (must pass before any speed claim):** SYCL DIS vs
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
- **Speed gate (v1 success criterion):** SYCL DIS (FAST preset) ≥ 3×
  faster than OpenCV CPU DIS-FAST at 720p and at 1080p on the named
  Intel target SKU, including host↔device transfer in wall time;
  ≥ 30 FPS wall at 720p and ≥ 15 FPS wall at 1080p. If the 3× gate
  fails, the deliverable is still the parity-validated SYCL
  implementation + the measurement, not a claimed speedup.
- **Reporting gate:** every speed number accompanied by host (CPU model,
  GPU model, driver, oneAPI version, OpenCV version + build flags),
  resolution, preset/parameters, warm-up/repetitions, and kernel-vs-wall
  split. Numbers without this context are not accepted into the report.

SIFT's benchmark discipline applies here too: include conversion /
upload / extraction and owned host outputs; exclude one-time
context/workspace setup and decode/resize outside the timed path;
prefer fresh processes, counterbalanced backend order, and enough
samples for median/p95.

## 9. Integration

- **DL Streamer:** proposed new element `gvaopticalflow` (name to be
  confirmed — no such element exists in the 2026.0/2026.2 element
  lists), e.g. `decodebin3 ! gvaopticalflow preset=fast device=GPU`,
  emitting dense flow as metadata consumable by `gvatrack`
  (motion-aware association), `gvamotiondetect` (replace/augment block
  motion with flow-magnitude ROIs), and `gvawatermark`. The existing
  `gvamotiondetect` is lightweight motion detection on NV12 frames —
  frame-differencing / block motion, not dense flow — it is the closest
  existing element and the template, not a substitute.
- **Scenescape:** flow is upstream, not inside SceneScape. Better
  per-object velocity (dense flow averaged over a detection box, or
  sparse LK tracks on the object) and motion-based ROI gating before
  detection. SceneScape's Controller fuses detections and tracks
  objects (100 objects @15fps on Core Ultra, per the 2025.2 release
  note) — it consumes detections/tracks, not pixel flow.
- **ORB-SLAM3 / SIFT:** sparse PyrLK as the SLAM-facing deliverable —
  track SIFT/ORB keypoints between frames, flag dynamic points by
  flow/epipolar inconsistency. Stock ORB-SLAM3 tracks by ORB descriptor
  matching, not LK; LK is a literature extension. Dense flow gives a
  motion prior for SIFT matching (predict keypoint positions, shrink
  the search window, reject flow-inconsistent matches) — a follow-on
  experiment, not assumed in v1.
- **Use cases:** motion ROI / smart motion detection (DIS fast);
  object tracking (sparse PyrLK, DIS averaged over boxes);
  video stabilisation (sparse PyrLK → homography, smoothed);
  frame interpolation / FRUC (dense DIS or dense PyrLK, forward +
  backward flow, forward-backward consistency, splatting/warping —
  Nvidia FRUC is 4.41 ms @1080p on an RTX 4090);
  VSLAM / robotics (sparse PyrLK); video-analytics pre-filter
  (DIS ultrafast, gate expensive inference to frames/ROIs with motion).

## 10. Roadmap

- **P0 — Spike (days):** confirm in-repo that no flow code exists
  (`grep -ri "optical.flow\|DISOpticalFlow\|calcOpticalFlow"` across
  `edge-ai-libraries` / `edge-ai-suites`); confirm the SIFT pyramid
  code is reusable; run OpenCV CPU DIS/Farneback/PyrLK on the target
  SKU and record the baseline; fix the target SKU, driver, and oneAPI
  version; confirm whether Python bindings are required in v1.
  Exit: baseline numbers + a named SKU, or a written "no baseline"
  note.
- **P1 — DIS SYCL (the v1 deliverable):** pyramid + patch inverse
  search + densification + variational refinement, OpenCV-compatible
  `calc()` API, CPU fallback, parity harness on a 50-pair Sintel
  subset, then full Sintel + KITTI accuracy vs OpenCV CPU, then timing
  at 720p/1080p. Exit: parity gate passed, speed gate measured
  honestly either way.
- **P2 — Farneback + sparse PyrLK:** Farneback as second dense
  implementation; sparse PyrLK for tracking / SLAM. Reuse the P1
  pyramid and harness. Exit: both parity-gated against OpenCV CPU.
- **P3 — Pipeline integration:** `gvaopticalflow` DL Streamer element,
  Python wheel, samples (stabilisation, motion ROI, tracking demo),
  root-README entry under Computer Vision Primitives. Exit: an
  end-to-end DL Streamer pipeline runs flow GPU-resident with no host
  copy per frame.
- **P4 — Neural flow (accuracy reference):** port SEA-RAFT-S to
  OpenVINO, benchmark on Arc / Core Ultra GPU, use as the accuracy
  reference for DIS. Exit: a measured OpenVINO number, not a claim.

Build / CI, following SIFT: `cmake -S . -B build
-DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release
-DOPTICALFLOW_ENABLE_SYCL=ON -DOPTICALFLOW_ENABLE_OPENCL=ON
-DOPTICALFLOW_BUILD_TESTS=ON`, then `cmake --build build --parallel`
and `ctest --test-dir build --output-on-failure`. Scoped GitHub Actions
configure/build without GPU backends (no Intel GPU runners in CI;
OpenCL/SYCL CTest and Arc timing are lab gates). Apache-2.0, DCO
sign-off, fork from `main`, PRs as the contribution path — same as
CONTRIBUTING.md.

## 11. Open questions

1. Target Intel SKU / driver / oneAPI version for the benchmark — not
   named yet. All speed gates in §8 are conditional on naming one
   (propose Core Ultra Series 2 + Arc B580 as the default pair, to be
   confirmed).
2. Python bindings in v1? SIFT has them; DL Streamer Python is a
   likely user. Changes P1 scope.
3. DL Streamer element name and metadata contract (`gvaopticalflow`
   is a proposal, not a found API).
4. Does DIS / Farneback / PyrLK have a working `UMat`/OpenCL path in
   OpenCV on the target SKU? Verify empirically; do not assume.
5. Nvidia SDK beyond 5.0 / Blackwell support — primary 5.0 docs list
   Turing/Ampere/Ada only; verify against the current SDK download
   before asserting.
6. In-repo flow code — the file-path search found none, but GitHub
   code search (inside file contents) requires sign-in and was not
   run; P0 grep is still needed.
7. SEA-RAFT / RAFT on Intel GPU via OpenVINO — no published Intel-GPU
   benchmark was found; Phase-2 feasibility is unverified.

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
