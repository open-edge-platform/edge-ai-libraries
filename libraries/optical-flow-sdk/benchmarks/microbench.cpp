// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Unified CPU / OpenCL / SYCL timing harness.
//   ./microbench [--backend cpu|opencl|sycl|all]
//                [--mode host|resident|both]
//                [--preset fast|medium|slow]

#include "optical_flow_sdk/optical_flow.hpp"
#include "optical_flow_sdk/version.hpp"

#if OPTICALFLOW_HAS_OPENCL
#include "optical_flow_sdk/opencl_optical_flow.hpp"
#endif
#if OPTICALFLOW_HAS_SYCL
#include "optical_flow_sdk/sycl_optical_flow.hpp"
#endif

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

namespace {

using optical_flow_sdk::Backend;
using optical_flow_sdk::ImageView;
using optical_flow_sdk::Preset;

// OpenCV DIS-Fast baselines (Core Ultra 7 255H, 2026-11-09).
struct Case {
  int w;
  int h;
  double opencv_ms;
};

constexpr Case kCases[] = {{1280, 720, 11.9}, {1920, 1080, 24.0}};
constexpr Case kHostExtra[] = {{640, 360, 0.0}}; // no OpenCV column

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

std::vector<std::uint8_t> shift(const std::vector<std::uint8_t> &src, int w, int h, int dx) {
  std::vector<std::uint8_t> dst(src.size(), 0);
  for (int y = 0; y < h; ++y) {
    for (int x = std::max(0, dx); x < w; ++x)
      dst[static_cast<std::size_t>(y) * w + x] = src[static_cast<std::size_t>(y) * w + (x - dx)];
  }
  return dst;
}

double run_host(Backend backend, Preset preset, int w, int h, int warmup, int iters) {
  const auto prev = make_textured(w, h);
  const auto next = shift(prev, w, h, 3);
  optical_flow_sdk::OpticalFlow of(backend, preset);
  optical_flow_sdk::FlowField flow;
  ImageView p{prev.data(), w, h, 0};
  ImageView n{next.data(), w, h, 0};
  for (int i = 0; i < warmup; ++i)
    of.calc(p, n, flow);
  const auto t0 = std::chrono::steady_clock::now();
  for (int i = 0; i < iters; ++i)
    of.calc(p, n, flow);
  const auto t1 = std::chrono::steady_clock::now();
  return std::chrono::duration<double, std::milli>(t1 - t0).count() / iters;
}

void print_host(const char *tag, int w, int h, double ms, double opencv_ms) {
  std::cout << w << "x" << h << " " << tag << "_ms=" << ms << " fps~=" << (1000.0 / ms);
  if (opencv_ms > 0.0)
    std::cout << " vs_opencv=" << (opencv_ms / ms) << "x";
  std::cout << "\n";
}

#if OPTICALFLOW_HAS_OPENCL
void run_opencl_resident(Preset preset) {
  optical_flow_sdk::OpenCLOpticalFlow of(preset);
  for (const auto &c : kCases) {
    const auto prev = make_textured(c.w, c.h);
    const auto next = shift(prev, c.w, c.h, 3);
    auto d_prev = of.create_u8_image(c.w, c.h);
    auto d_next = of.create_u8_image(c.w, c.h);
    auto d_flow = of.create_flow_buffer(c.w, c.h);
    of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
    of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
    of.finish();

    for (int i = 0; i < 8; ++i)
      of.calc_device(d_prev, d_next, d_flow);

    constexpr int kIters = 40;
    const auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < kIters; ++i)
      of.calc_device(d_prev, d_next, d_flow);
    const auto t1 = std::chrono::steady_clock::now();
    const double ms =
        std::chrono::duration<double, std::milli>(t1 - t0).count() / static_cast<double>(kIters);

    for (int i = 0; i < 5; ++i) {
      of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
      of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
      of.calc_device(d_prev, d_next, d_flow);
    }
    const auto p0 = std::chrono::steady_clock::now();
    for (int i = 0; i < kIters; ++i) {
      of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
      of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
      of.calc_device(d_prev, d_next, d_flow);
    }
    const auto p1 = std::chrono::steady_clock::now();
    const double pipe_ms =
        std::chrono::duration<double, std::milli>(p1 - p0).count() / static_cast<double>(kIters);

    std::cout << c.w << "x" << c.h << " opencl_resident_ms=" << ms << " fps~=" << (1000.0 / ms)
              << " vs_opencv=" << (c.opencv_ms / ms) << "x"
              << " pipeline_H2D_no_D2H_ms=" << pipe_ms
              << " pipeline_vs_opencv=" << (c.opencv_ms / pipe_ms) << "x\n";
  }
}
#endif

#if OPTICALFLOW_HAS_SYCL
void run_sycl_resident(Preset preset) {
  for (const auto &c : kCases) {
    // Fresh engine per resolution so workspace teardown stays clean on iGPU.
    optical_flow_sdk::SyclOpticalFlow of(preset);
    const auto prev = make_textured(c.w, c.h);
    const auto next = shift(prev, c.w, c.h, 3);
    auto d_prev = of.create_u8_image(c.w, c.h);
    auto d_next = of.create_u8_image(c.w, c.h);
    auto d_flow = of.create_flow_buffer(c.w, c.h);
    of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
    of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
    of.finish();

    for (int i = 0; i < 5; ++i)
      of.calc_device(d_prev, d_next, d_flow);
    of.finish();

    constexpr int kIters = 20;
    const auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < kIters; ++i)
      of.calc_device(d_prev, d_next, d_flow);
    of.finish();
    const auto t1 = std::chrono::steady_clock::now();
    const double ms =
        std::chrono::duration<double, std::milli>(t1 - t0).count() / static_cast<double>(kIters);

    for (int i = 0; i < 3; ++i) {
      of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
      of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
      of.calc_device(d_prev, d_next, d_flow);
    }
    of.finish();
    const auto p0 = std::chrono::steady_clock::now();
    for (int i = 0; i < kIters; ++i) {
      of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
      of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
      of.calc_device(d_prev, d_next, d_flow);
    }
    of.finish();
    const auto p1 = std::chrono::steady_clock::now();
    const double pipe_ms =
        std::chrono::duration<double, std::milli>(p1 - p0).count() / static_cast<double>(kIters);

    std::cout << c.w << "x" << c.h << " sycl_resident_ms=" << ms << " fps~=" << (1000.0 / ms)
              << " vs_opencv=" << (c.opencv_ms / ms) << "x"
              << " pipeline_H2D_no_D2H_ms=" << pipe_ms
              << " pipeline_vs_opencv=" << (c.opencv_ms / pipe_ms) << "x\n";
  }
}
#endif

void usage() {
  std::cout << "usage: microbench [--backend cpu|opencl|sycl|all]\n"
               "                   [--mode host|resident|both]\n"
               "                   [--preset fast|medium|slow]\n";
}

bool parse_backend(const char *s, bool &cpu, bool &opencl, bool &sycl) {
  cpu = opencl = sycl = false;
  if (std::strcmp(s, "all") == 0) {
    cpu = true;
    opencl = OPTICALFLOW_HAS_OPENCL != 0;
    sycl = OPTICALFLOW_HAS_SYCL != 0;
    return true;
  }
  if (std::strcmp(s, "cpu") == 0) {
    cpu = true;
    return true;
  }
  if (std::strcmp(s, "opencl") == 0) {
    opencl = true;
    return true;
  }
  if (std::strcmp(s, "sycl") == 0) {
    sycl = true;
    return true;
  }
  return false;
}

bool parse_preset(const char *s, Preset &preset) {
  if (std::strcmp(s, "fast") == 0) {
    preset = Preset::Fast;
    return true;
  }
  if (std::strcmp(s, "medium") == 0) {
    preset = Preset::Medium;
    return true;
  }
  if (std::strcmp(s, "slow") == 0) {
    preset = Preset::Slow;
    return true;
  }
  return false;
}

} // namespace

int main(int argc, char **argv) {
  bool want_cpu = true;
  bool want_opencl = OPTICALFLOW_HAS_OPENCL != 0;
  bool want_sycl = OPTICALFLOW_HAS_SYCL != 0;
  bool mode_host = true;
  bool mode_resident = true;
  Preset preset = Preset::Fast;

  for (int i = 1; i < argc; ++i) {
    const std::string a = argv[i];
    if (a == "--help" || a == "-h") {
      usage();
      return EXIT_SUCCESS;
    }
    if (a == "--backend" && i + 1 < argc) {
      if (!parse_backend(argv[++i], want_cpu, want_opencl, want_sycl)) {
        usage();
        return EXIT_FAILURE;
      }
      continue;
    }
    if (a == "--mode" && i + 1 < argc) {
      const char *m = argv[++i];
      mode_host = mode_resident = false;
      if (std::strcmp(m, "host") == 0)
        mode_host = true;
      else if (std::strcmp(m, "resident") == 0)
        mode_resident = true;
      else if (std::strcmp(m, "both") == 0)
        mode_host = mode_resident = true;
      else {
        usage();
        return EXIT_FAILURE;
      }
      continue;
    }
    if (a == "--preset" && i + 1 < argc) {
      if (!parse_preset(argv[++i], preset)) {
        usage();
        return EXIT_FAILURE;
      }
      continue;
    }
    usage();
    return EXIT_FAILURE;
  }

  if (want_opencl && !OPTICALFLOW_HAS_OPENCL) {
    std::cerr << "error: OpenCL backend not built (OPTICALFLOW_ENABLE_OPENCL=OFF)\n";
    return EXIT_FAILURE;
  }
  if (want_sycl && !OPTICALFLOW_HAS_SYCL) {
    std::cerr << "error: SYCL backend not built (OPTICALFLOW_ENABLE_SYCL=OFF)\n";
    return EXIT_FAILURE;
  }
  if (mode_resident && !want_opencl && !want_sycl && !want_cpu) {
    std::cerr << "error: nothing to run\n";
    return EXIT_FAILURE;
  }
  if (mode_resident && want_cpu && !want_opencl && !want_sycl && !mode_host) {
    std::cerr << "error: CPU has no resident path; use --mode host\n";
    return EXIT_FAILURE;
  }

  std::cout << "microbench preset=" << optical_flow_sdk::preset_name(preset)
            << " backends=" << (want_cpu ? "cpu " : "") << (want_opencl ? "opencl " : "")
            << (want_sycl ? "sycl " : "") << "mode="
            << (mode_host && mode_resident ? "both" : mode_host ? "host" : "resident") << "\n";

  if (mode_host) {
    if (want_cpu) {
      for (const auto &c : kHostExtra) {
        const double ms = run_host(Backend::Cpu, preset, c.w, c.h, 2, 5);
        print_host("cpu", c.w, c.h, ms, 0.0);
      }
      for (const auto &c : kCases) {
        const double ms = run_host(Backend::Cpu, preset, c.w, c.h, 3, 10);
        print_host("cpu", c.w, c.h, ms, c.opencv_ms);
      }
    }
#if OPTICALFLOW_HAS_OPENCL
    if (want_opencl) {
      for (const auto &c : kCases) {
        const double ms = run_host(Backend::OpenCL, preset, c.w, c.h, 5, 20);
        print_host("opencl_host", c.w, c.h, ms, c.opencv_ms);
      }
    }
#endif
#if OPTICALFLOW_HAS_SYCL
    if (want_sycl) {
      for (const auto &c : kCases) {
        const double ms = run_host(Backend::Sycl, preset, c.w, c.h, 8, 30);
        print_host("sycl_host", c.w, c.h, ms, c.opencv_ms);
      }
    }
#endif
  }

  if (mode_resident) {
#if OPTICALFLOW_HAS_OPENCL
    if (want_opencl)
      run_opencl_resident(preset);
#endif
#if OPTICALFLOW_HAS_SYCL
    if (want_sycl)
      run_sycl_resident(preset);
#endif
  }

  return EXIT_SUCCESS;
}
