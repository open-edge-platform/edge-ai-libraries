// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// NVOFA FPS + KITTI Fl-all on an Nvidia Optical Flow host.
// Standalone (does not link optical_flow_sdk). Requires CUDA toolkit,
// NVIDIAOpticalFlowSDK headers, and libnvidia-opticalflow.
//
// Build (example on gklab-233-162):
//   source ~/cuda/env.sh
//   g++ -O2 -std=c++17 benchmarks/microbench_nvofa.cpp -o microbench_nvofa \
//     -I"$NVIDIA_OPTICAL_FLOW_SDK_ROOT" -I"$CUDA_HOME/include" \
//     -DSTB_IMAGE_IMPLEMENTATION \
//     -L"$CUDA_HOME/lib" -lcudart -lcuda -lnvidia-opticalflow \
//     -Wl,-rpath,"$CUDA_HOME/lib"
//
// Usage:
//   ./microbench_nvofa                  # FPS table @720p/1080p Slow/Medium/Fast
//   ./microbench_nvofa --kitti ROOT      # + KITTI train Fl-all (image_2 + flow_occ)

#include <cuda.h>
#include <cuda_runtime.h>

#include "nvOpticalFlowCommon.h"
#include "nvOpticalFlowCuda.h"

#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

struct PresetCase {
  const char *name;
  NV_OF_PERF_LEVEL level;
};

constexpr PresetCase kPresets[] = {
    {"Slow", NV_OF_PERF_LEVEL_SLOW},
    {"Medium", NV_OF_PERF_LEVEL_MEDIUM},
    {"Fast", NV_OF_PERF_LEVEL_FAST},
};

void check_cuda(cudaError_t e, const char *what) {
  if (e != cudaSuccess) {
    std::cerr << what << ": " << cudaGetErrorString(e) << "\n";
    std::exit(2);
  }
}

void check_of(NV_OF_STATUS st, const char *what) {
  if (st != NV_OF_SUCCESS) {
    std::cerr << what << ": NV_OF_STATUS=" << static_cast<int>(st) << "\n";
    std::exit(2);
  }
}

std::vector<std::uint8_t> make_textured(int w, int h) {
  std::vector<std::uint8_t> img(static_cast<std::size_t>(w) * h);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const float v = 128.0f + 60.0f * std::sin(0.21f * x) * std::cos(0.17f * y);
      img[static_cast<std::size_t>(y) * w + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  return img;
}

std::vector<std::uint8_t> shift_x(const std::vector<std::uint8_t> &src, int w, int h, int dx) {
  std::vector<std::uint8_t> dst(src.size(), 0);
  for (int y = 0; y < h; ++y) {
    for (int x = std::max(0, dx); x < w; ++x)
      dst[static_cast<std::size_t>(y) * w + x] = src[static_cast<std::size_t>(y) * w + (x - dx)];
  }
  return dst;
}

int align_up(int v, int a) { return (v + a - 1) / a * a; }

struct NvOfSession {
  NV_OF_CUDA_API_FUNCTION_LIST api{};
  NvOFHandle h = nullptr;
  int width = 0;
  int height = 0;
  int grid = 4;
  int out_w = 0;
  int out_h = 0;
  NvOFGPUBufferHandle in0 = nullptr;
  NvOFGPUBufferHandle in1 = nullptr;
  NvOFGPUBufferHandle out = nullptr;
  CUdeviceptr in0_ptr = 0;
  CUdeviceptr in1_ptr = 0;
  CUdeviceptr out_ptr = 0;
  uint32_t in_stride = 0;
  uint32_t out_stride = 0;
};

void destroy_session(NvOfSession &s) {
  if (!s.h)
    return;
  if (s.in0)
    s.api.nvOFDestroyGPUBufferCuda(s.in0);
  if (s.in1)
    s.api.nvOFDestroyGPUBufferCuda(s.in1);
  if (s.out)
    s.api.nvOFDestroyGPUBufferCuda(s.out);
  s.api.nvOFDestroy(s.h);
  s = {};
}

NvOfSession create_session(CUcontext ctx, int width, int height, NV_OF_PERF_LEVEL preset,
                           int grid = 4) {
  NvOfSession s;
  s.width = width;
  s.height = height;
  s.grid = grid;
  s.out_w = width / grid;
  s.out_h = height / grid;
  check_of(NvOFAPICreateInstanceCuda(NV_OF_API_VERSION, &s.api), "NvOFAPICreateInstanceCuda");
  check_of(s.api.nvCreateOpticalFlowCuda(ctx, &s.h), "nvCreateOpticalFlowCuda");

  NV_OF_INIT_PARAMS init{};
  init.width = static_cast<uint32_t>(width);
  init.height = static_cast<uint32_t>(height);
  init.outGridSize = static_cast<NV_OF_OUTPUT_VECTOR_GRID_SIZE>(grid);
  init.hintGridSize = NV_OF_HINT_VECTOR_GRID_SIZE_UNDEFINED;
  init.mode = NV_OF_MODE_OPTICALFLOW;
  init.perfLevel = preset;
  init.enableExternalHints = NV_OF_FALSE;
  init.enableOutputCost = NV_OF_FALSE;
  init.hPrivData = nullptr;
  init.disparityRange = NV_OF_STEREO_DISPARITY_RANGE_UNDEFINED;
  init.enableRoi = NV_OF_FALSE;
  check_of(s.api.nvOFInit(s.h, &init), "nvOFInit");

  NV_OF_BUFFER_DESCRIPTOR idesc{};
  idesc.width = static_cast<uint32_t>(width);
  idesc.height = static_cast<uint32_t>(height);
  idesc.bufferUsage = NV_OF_BUFFER_USAGE_INPUT;
  idesc.bufferFormat = NV_OF_BUFFER_FORMAT_GRAYSCALE8;
  check_of(s.api.nvOFCreateGPUBufferCuda(s.h, &idesc, NV_OF_CUDA_BUFFER_TYPE_CUDEVICEPTR, &s.in0),
           "create in0");
  check_of(s.api.nvOFCreateGPUBufferCuda(s.h, &idesc, NV_OF_CUDA_BUFFER_TYPE_CUDEVICEPTR, &s.in1),
           "create in1");

  NV_OF_BUFFER_DESCRIPTOR odesc{};
  odesc.width = static_cast<uint32_t>(s.out_w);
  odesc.height = static_cast<uint32_t>(s.out_h);
  odesc.bufferUsage = NV_OF_BUFFER_USAGE_OUTPUT;
  odesc.bufferFormat = NV_OF_BUFFER_FORMAT_SHORT2;
  check_of(s.api.nvOFCreateGPUBufferCuda(s.h, &odesc, NV_OF_CUDA_BUFFER_TYPE_CUDEVICEPTR, &s.out),
           "create out");

  s.in0_ptr = s.api.nvOFGPUBufferGetCUdeviceptr(s.in0);
  s.in1_ptr = s.api.nvOFGPUBufferGetCUdeviceptr(s.in1);
  s.out_ptr = s.api.nvOFGPUBufferGetCUdeviceptr(s.out);

  // NVOFA strideXInBytes is the CUDA row pitch; strideYInBytes is height in rows.
  NV_OF_CUDA_BUFFER_STRIDE_INFO si{};
  check_of(s.api.nvOFGPUBufferGetStrideInfo(s.in0, &si), "stride in");
  s.in_stride = si.strideInfo[0].strideXInBytes;
  check_of(s.api.nvOFGPUBufferGetStrideInfo(s.out, &si), "stride out");
  s.out_stride = si.strideInfo[0].strideXInBytes;
  return s;
}

void upload_gray(const NvOfSession &s, CUdeviceptr dst, const std::uint8_t *src) {
  // src is tightly packed w*h; device may have larger pitch.
  if (s.in_stride == static_cast<uint32_t>(s.width)) {
    check_cuda(cudaMemcpy(reinterpret_cast<void *>(dst), src,
                          static_cast<size_t>(s.width) * s.height, cudaMemcpyHostToDevice),
               "H2D gray");
  } else {
    check_cuda(cudaMemcpy2D(reinterpret_cast<void *>(dst), s.in_stride, src, s.width, s.width,
                            s.height, cudaMemcpyHostToDevice),
               "H2D gray pitched");
  }
}

void execute(const NvOfSession &s, bool disable_temporal) {
  NV_OF_EXECUTE_INPUT_PARAMS in{};
  in.inputFrame = s.in0;
  in.referenceFrame = s.in1;
  in.externalHints = nullptr;
  in.disableTemporalHints = disable_temporal ? NV_OF_TRUE : NV_OF_FALSE;
  in.padding = 0;
  in.hPrivData = nullptr;
  in.padding2 = 0;
  in.numRois = 0;
  in.roiData = nullptr;
  NV_OF_EXECUTE_OUTPUT_PARAMS out{};
  out.outputBuffer = s.out;
  out.outputCostBuffer = nullptr;
  out.hPrivData = nullptr;
  check_of(s.api.nvOFExecute(s.h, &in, &out), "nvOFExecute");
}

double bench_fps(NvOfSession &s, const std::uint8_t *prev, const std::uint8_t *next, int warm,
                 int iters, bool disable_temporal) {
  upload_gray(s, s.in0_ptr, prev);
  upload_gray(s, s.in1_ptr, next);
  check_cuda(cudaDeviceSynchronize(), "sync upload");
  for (int i = 0; i < warm; ++i) {
    execute(s, disable_temporal);
  }
  check_cuda(cudaDeviceSynchronize(), "sync warm");
  const auto t0 = std::chrono::steady_clock::now();
  for (int i = 0; i < iters; ++i)
    execute(s, disable_temporal);
  check_cuda(cudaDeviceSynchronize(), "sync timed");
  const auto t1 = std::chrono::steady_clock::now();
  const double ms =
      std::chrono::duration<double, std::milli>(t1 - t0).count() / static_cast<double>(iters);
  return 1000.0 / ms;
}

std::vector<NV_OF_FLOW_VECTOR> download_flow(const NvOfSession &s) {
  std::vector<NV_OF_FLOW_VECTOR> host(static_cast<std::size_t>(s.out_w) * s.out_h);
  if (s.out_stride == static_cast<uint32_t>(s.out_w) * sizeof(NV_OF_FLOW_VECTOR)) {
    check_cuda(cudaMemcpy(host.data(), reinterpret_cast<void *>(s.out_ptr),
                          host.size() * sizeof(NV_OF_FLOW_VECTOR), cudaMemcpyDeviceToHost),
               "D2H flow");
  } else {
    check_cuda(cudaMemcpy2D(host.data(), s.out_w * sizeof(NV_OF_FLOW_VECTOR),
                            reinterpret_cast<void *>(s.out_ptr), s.out_stride,
                            s.out_w * sizeof(NV_OF_FLOW_VECTOR), s.out_h, cudaMemcpyDeviceToHost),
               "D2H flow pitched");
  }
  return host;
}

// Nearest upsample of S10.5 grid flow to dense float dx/dy (pixels).
void upsample_s105(const std::vector<NV_OF_FLOW_VECTOR> &flow_grid, int out_w, int out_h,
                   int grid_size, int img_w, int img_h, std::vector<float> &dx,
                   std::vector<float> &dy) {
  dx.assign(static_cast<std::size_t>(img_w) * img_h, 0.f);
  dy.assign(static_cast<std::size_t>(img_w) * img_h, 0.f);
  for (int y = 0; y < img_h; ++y) {
    const int gy = std::min(y / grid_size, out_h - 1);
    for (int x = 0; x < img_w; ++x) {
      const int gx = std::min(x / grid_size, out_w - 1);
      const auto &v = flow_grid[static_cast<std::size_t>(gy) * out_w + gx];
      dx[static_cast<std::size_t>(y) * img_w + x] = static_cast<float>(v.flowx) / 32.0f;
      dy[static_cast<std::size_t>(y) * img_w + x] = static_cast<float>(v.flowy) / 32.0f;
    }
  }
}

bool load_gray_png(const fs::path &path, int want_w, int want_h, std::vector<std::uint8_t> &out) {
  int w = 0, h = 0, c = 0;
  unsigned char *img = stbi_load(path.string().c_str(), &w, &h, &c, 1);
  if (!img)
    return false;
  out.assign(static_cast<std::size_t>(want_w) * want_h, 0);
  const int copy_w = std::min(w, want_w);
  const int copy_h = std::min(h, want_h);
  for (int y = 0; y < copy_h; ++y)
    std::memcpy(out.data() + static_cast<std::size_t>(y) * want_w, img + static_cast<std::size_t>(y) * w,
                static_cast<std::size_t>(copy_w));
  stbi_image_free(img);
  return true;
}

bool load_kitti_flow(const fs::path &path, int &w, int &h, std::vector<float> &dx,
                     std::vector<float> &dy, std::vector<std::uint8_t> &valid) {
  int c = 0;
  stbi_us *img = stbi_load_16(path.string().c_str(), &w, &h, &c, 3);
  if (!img || c < 3)
    return false;
  dx.resize(static_cast<std::size_t>(w) * h);
  dy.resize(static_cast<std::size_t>(w) * h);
  valid.resize(static_cast<std::size_t>(w) * h);
  for (int i = 0; i < w * h; ++i) {
    // stb loads RGB; KITTI packs R=fx, G=fy, B=valid in the file's RGB order.
    const stbi_us r = img[i * 3 + 0];
    const stbi_us g = img[i * 3 + 1];
    const stbi_us b = img[i * 3 + 2];
    dx[static_cast<std::size_t>(i)] = (static_cast<float>(r) - 32768.0f) / 64.0f;
    dy[static_cast<std::size_t>(i)] = (static_cast<float>(g) - 32768.0f) / 64.0f;
    valid[static_cast<std::size_t>(i)] = b > 0 ? 1 : 0;
  }
  stbi_image_free(img);
  return true;
}

struct FlStats {
  double fl_all_pct = 0.0;
  double epe = 0.0;
  long long bad = 0;
  long long n = 0;
};

FlStats fl_all(const std::vector<float> &pdx, const std::vector<float> &pdy,
               const std::vector<float> &gdx, const std::vector<float> &gdy,
               const std::vector<std::uint8_t> &valid, int img_w, int img_h, int native_w,
               int native_h) {
  FlStats s;
  double epe_sum = 0.0;
  const int eval_w = std::min(img_w, native_w);
  const int eval_h = std::min(img_h, native_h);
  for (int y = 0; y < eval_h; ++y) {
    for (int x = 0; x < eval_w; ++x) {
      const std::size_t gi = static_cast<std::size_t>(y) * native_w + x;
      const std::size_t pi = static_cast<std::size_t>(y) * img_w + x;
      if (!valid[gi])
        continue;
      const float ex = pdx[pi] - gdx[gi];
      const float ey = pdy[pi] - gdy[gi];
      const float epe = std::sqrt(ex * ex + ey * ey);
      if (!std::isfinite(epe))
        continue;
      const float mag = std::sqrt(gdx[gi] * gdx[gi] + gdy[gi] * gdy[gi]);
      ++s.n;
      epe_sum += epe;
      if (epe > 3.0f && epe > 0.05f * mag)
        ++s.bad;
    }
  }
  if (s.n > 0) {
    s.fl_all_pct = 100.0 * static_cast<double>(s.bad) / static_cast<double>(s.n);
    s.epe = epe_sum / static_cast<double>(s.n);
  }
  return s;
}

void run_fps(CUcontext ctx) {
  constexpr int kWarm = 20;
  constexpr int kIters = 100;
  const int sizes[][2] = {{1280, 720}, {1920, 1080}};
  std::cout << "=== NVOFA FPS (device-resident execute, synthetic pair, temporalHints=off) ===\n";
  std::cout << "host_gpu=RTX_5060 grid=4x4 warm=" << kWarm << " iters=" << kIters << "\n";
  for (const auto &sz : sizes) {
    const int w = sz[0], h = sz[1];
    const auto prev = make_textured(w, h);
    const auto next = shift_x(prev, w, h, 3);
    for (const auto &p : kPresets) {
      auto s = create_session(ctx, w, h, p.level, 4);
      const double fps = bench_fps(s, prev.data(), next.data(), kWarm, kIters, true);
      std::cout << w << "x" << h << " preset=" << p.name << " fps=" << fps << "\n";
      destroy_session(s);
    }
  }
}

void run_kitti(CUcontext ctx, const fs::path &root, int max_pairs) {
  const fs::path img_dir = root / "training" / "image_2";
  const fs::path flow_dir = root / "training" / "flow_occ";
  if (!fs::is_directory(img_dir) || !fs::is_directory(flow_dir)) {
    std::cerr << "expected " << img_dir << " and " << flow_dir << "\n";
    std::exit(1);
  }

  std::vector<std::string> ids;
  for (const auto &e : fs::directory_iterator(flow_dir)) {
    if (!e.is_regular_file())
      continue;
    const auto name = e.path().filename().string();
    if (name.size() >= 7 && name.substr(name.size() - 7) == "_10.png")
      ids.push_back(name.substr(0, name.size() - 7));
  }
  std::sort(ids.begin(), ids.end());
  if (max_pairs > 0 && static_cast<int>(ids.size()) > max_pairs)
    ids.resize(static_cast<std::size_t>(max_pairs));

  std::cout << "=== NVOFA KITTI train Fl-all (grid=4x4, temporalHints=off) ===\n";
  std::cout << "pairs=" << ids.size() << " root=" << root << "\n";

  for (const auto &p : kPresets) {
    long long bad = 0, n = 0;
    double epe_sum = 0.0;
    int used = 0;
    for (const auto &id : ids) {
      const fs::path f10 = img_dir / (id + "_10.png");
      const fs::path f11 = img_dir / (id + "_11.png");
      const fs::path gt = flow_dir / (id + "_10.png");
      int gw = 0, gh = 0;
      std::vector<float> gdx, gdy;
      std::vector<std::uint8_t> valid;
      if (!load_kitti_flow(gt, gw, gh, gdx, gdy, valid)) {
        std::cerr << "skip bad gt " << gt << "\n";
        continue;
      }
      // NVOFA likes multiples of grid; pad up.
      const int w = align_up(gw, 4);
      const int h = align_up(gh, 4);
      std::vector<std::uint8_t> prev, next;
      if (!load_gray_png(f10, w, h, prev) || !load_gray_png(f11, w, h, next)) {
        std::cerr << "skip bad images " << id << "\n";
        continue;
      }
      auto s = create_session(ctx, w, h, p.level, 4);
      upload_gray(s, s.in0_ptr, prev.data());
      upload_gray(s, s.in1_ptr, next.data());
      execute(s, true);
      check_cuda(cudaDeviceSynchronize(), "sync kitti");
      const auto grid = download_flow(s);
      std::vector<float> pdx, pdy;
      upsample_s105(grid, s.out_w, s.out_h, s.grid, w, h, pdx, pdy);
      const FlStats st = fl_all(pdx, pdy, gdx, gdy, valid, w, h, gw, gh);
      bad += st.bad;
      n += st.n;
      epe_sum += st.epe * static_cast<double>(st.n);
      ++used;
      destroy_session(s);
    }
    const double fl = n ? 100.0 * static_cast<double>(bad) / static_cast<double>(n) : 0.0;
    const double epe = n ? epe_sum / static_cast<double>(n) : 0.0;
    std::cout << "preset=" << p.name << " pairs=" << used << " fl_all_pct=" << fl
              << " epe=" << epe << " n_valid=" << n << "\n";
  }
}

} // namespace

int main(int argc, char **argv) {
  std::string kitti;
  int max_pairs = 0;
  bool fps = true;
  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--kitti") == 0 && i + 1 < argc)
      kitti = argv[++i];
    else if (std::strcmp(argv[i], "--max-pairs") == 0 && i + 1 < argc)
      max_pairs = std::atoi(argv[++i]);
    else if (std::strcmp(argv[i], "--no-fps") == 0)
      fps = false;
    else if (std::strcmp(argv[i], "--help") == 0) {
      std::cout << "Usage: microbench_nvofa [--kitti ROOT] [--max-pairs N] [--no-fps]\n";
      return 0;
    }
  }

  check_cuda(cudaFree(0), "cudaFree(0)");
  CUcontext ctx = nullptr;
  if (cuCtxGetCurrent(&ctx) != CUDA_SUCCESS || !ctx) {
    std::cerr << "no CUDA context\n";
    return 2;
  }

  int driver = 0, runtime = 0;
  cudaDriverGetVersion(&driver);
  cudaRuntimeGetVersion(&runtime);
  cudaDeviceProp prop{};
  cudaGetDeviceProperties(&prop, 0);
  std::cout << "gpu=" << prop.name << " sm_" << prop.major << prop.minor
            << " driver_cuda=" << driver << " runtime_cuda=" << runtime << "\n";

  if (fps)
    run_fps(ctx);
  if (!kitti.empty())
    run_kitti(ctx, kitti, max_pairs);
  return 0;
}
