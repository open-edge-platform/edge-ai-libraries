// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Offline EPE harness. Without dataset args, runs a synthetic textured shift
// and writes/reads a temporary .flo to exercise the Middlebury I/O path.
// With --gt foo.flo --pred bar.flo, reports banded EPE only (no images needed).

#include "optical_flow_sdk/metrics.hpp"
#include "optical_flow_sdk/optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

void print_stats(const char *label, const optical_flow_sdk::EpeStats &s) {
  std::cout << label << " mean_epe=" << s.mean << " n=" << s.count
            << " s0-10=" << s.mean_s0_10 << " s10-40=" << s.mean_s10_40
            << " s40+=" << s.mean_s40p << "\n";
}

std::vector<std::uint8_t> make_textured(int w, int h) {
  std::vector<std::uint8_t> img(static_cast<std::size_t>(w) * h);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const float fx = 0.21f * x, fy = 0.17f * y;
      const float v = 128.0f + 60.0f * std::sin(fx) * std::cos(fy) +
                      40.0f * std::sin(fx * 2.3f + fy * 1.7f);
      img[static_cast<std::size_t>(y) * w + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  return img;
}

} // namespace

int main(int argc, char **argv) {
  std::string gt_path;
  std::string pred_path;
  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--gt") == 0 && i + 1 < argc)
      gt_path = argv[++i];
    else if (std::strcmp(argv[i], "--pred") == 0 && i + 1 < argc)
      pred_path = argv[++i];
    else if (std::strcmp(argv[i], "--help") == 0) {
      std::cout << "Usage: eval_flow_epe [--gt gt.flo --pred pred.flo]\n";
      return 0;
    }
  }

  if (!gt_path.empty() || !pred_path.empty()) {
    if (gt_path.empty() || pred_path.empty()) {
      std::cerr << "both --gt and --pred are required together\n";
      return 1;
    }
    const auto gt = optical_flow_sdk::read_flo(gt_path);
    const auto pred = optical_flow_sdk::read_flo(pred_path);
    print_stats("file", optical_flow_sdk::endpoint_error(pred, gt, 0));
    return 0;
  }

  constexpr int kW = 128;
  constexpr int kH = 96;
  constexpr int kDx = 3;
  constexpr int kDy = -2;
  const auto prev = make_textured(kW, kH);
  std::vector<std::uint8_t> next(prev.size(), 0);
  for (int y = 0; y < kH; ++y) {
    for (int x = 0; x < kW; ++x) {
      const int sx = x - kDx;
      const int sy = y - kDy;
      if (sx >= 0 && sy >= 0 && sx < kW && sy < kH)
        next[static_cast<std::size_t>(y) * kW + x] = prev[static_cast<std::size_t>(sy) * kW + sx];
    }
  }

  optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu, optical_flow_sdk::Preset::Fast);
  optical_flow_sdk::FlowField pred;
  of.calc({prev.data(), kW, kH, 0}, {next.data(), kW, kH, 0}, pred);

  optical_flow_sdk::FlowField gt;
  gt.allocate(kW, kH);
  for (int y = 0; y < kH; ++y)
    for (int x = 0; x < kW; ++x) {
      gt.dx(x, y) = static_cast<float>(kDx);
      gt.dy(x, y) = static_cast<float>(kDy);
    }

  const fs::path tmp = fs::temp_directory_path() / "optical_flow_sdk_eval_gt.flo";
  optical_flow_sdk::write_flo(tmp.string(), gt);
  const auto gt_roundtrip = optical_flow_sdk::read_flo(tmp.string());
  print_stats("synthetic_dis", optical_flow_sdk::endpoint_error(pred, gt_roundtrip, 16));
  fs::remove(tmp);
  return 0;
}
