// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// OpenCL video-clip FRUC demo: multi-frame pan → calc_device + warp_u8(t=0.5).
// Default: synthetic 720p/1080p clip (no decode deps). Optional packed gray file:
//   sample_fruc_video_opencl --raw W H N path.gray

#include "optical_flow_sdk/opencl_optical_flow.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {

std::vector<std::uint8_t> make_frame(int w, int h, float phase) {
  std::vector<std::uint8_t> img(static_cast<std::size_t>(w) * h);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const float fx = 0.045f * (static_cast<float>(x) + phase);
      const float fy = 0.037f * static_cast<float>(y);
      const float v = 128.0f + 55.0f * std::sin(fx) * std::cos(fy) +
                      35.0f * std::sin(fx * 2.1f + fy * 1.4f);
      img[static_cast<std::size_t>(y) * w + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  return img;
}

bool load_raw_clip(const std::string &path, int w, int h, int n,
                   std::vector<std::vector<std::uint8_t>> &frames) {
  std::ifstream in(path, std::ios::binary);
  if (!in)
    return false;
  const std::size_t frame_bytes = static_cast<std::size_t>(w) * h;
  frames.resize(static_cast<std::size_t>(n));
  for (int i = 0; i < n; ++i) {
    frames[static_cast<std::size_t>(i)].resize(frame_bytes);
    in.read(reinterpret_cast<char *>(frames[static_cast<std::size_t>(i)].data()),
            static_cast<std::streamsize>(frame_bytes));
    if (!in)
      return false;
  }
  return true;
}

void usage(const char *argv0) {
  std::cerr << "Usage: " << argv0 << " [720|1080] [frames=16]\n"
            << "       " << argv0 << " --raw W H N path.gray\n";
}

} // namespace

int main(int argc, char **argv) {
#if !OPTICALFLOW_HAS_OPENCL
  std::cerr << "OpenCL not enabled\n";
  return 1;
#else
  int w = 1280;
  int h = 720;
  int n_frames = 16;
  std::vector<std::vector<std::uint8_t>> frames;

  if (argc >= 2 && std::string(argv[1]) == "--raw") {
    if (argc < 6) {
      usage(argv[0]);
      return 2;
    }
    w = std::atoi(argv[2]);
    h = std::atoi(argv[3]);
    n_frames = std::atoi(argv[4]);
    if (w <= 0 || h <= 0 || n_frames < 2) {
      usage(argv[0]);
      return 2;
    }
    if (!load_raw_clip(argv[5], w, h, n_frames, frames)) {
      std::cerr << "failed to read raw gray clip " << argv[5] << "\n";
      return 1;
    }
  } else {
    if (argc >= 2) {
      const std::string a = argv[1];
      if (a == "1080") {
        w = 1920;
        h = 1080;
      } else if (a == "720") {
        w = 1280;
        h = 720;
      } else {
        usage(argv[0]);
        return 2;
      }
    }
    if (argc >= 3)
      n_frames = std::max(2, std::atoi(argv[2]));
    frames.reserve(static_cast<std::size_t>(n_frames));
    // ~2 px/frame horizontal pan across the clip.
    for (int i = 0; i < n_frames; ++i)
      frames.push_back(make_frame(w, h, static_cast<float>(i) * 2.0f));
  }

  optical_flow_sdk::OpenCLOpticalFlow of(optical_flow_sdk::Preset::Fast);
  auto d_prev = of.create_u8_image(w, h);
  auto d_next = of.create_u8_image(w, h);
  auto d_flow = of.create_flow_buffer(w, h);
  auto d_mid = of.create_u8_image(w, h);

  // Warmup
  of.upload_u8(d_prev, {frames[0].data(), w, h, 0});
  of.upload_u8(d_next, {frames[1].data(), w, h, 0});
  of.calc_device(d_prev, d_next, d_flow);
  of.warp_u8(d_prev, d_flow, d_mid, 0.5f);
  of.finish();

  const int pairs = n_frames - 1;
  const auto t0 = std::chrono::steady_clock::now();
  for (int i = 0; i < pairs; ++i) {
    of.upload_u8(d_prev, {frames[static_cast<std::size_t>(i)].data(), w, h, 0});
    of.upload_u8(d_next, {frames[static_cast<std::size_t>(i + 1)].data(), w, h, 0});
    of.calc_device(d_prev, d_next, d_flow);
    of.warp_u8(d_prev, d_flow, d_mid, 0.5f);
  }
  of.finish();
  const auto t1 = std::chrono::steady_clock::now();
  const double pipe_ms =
      std::chrono::duration<double, std::milli>(t1 - t0).count() / static_cast<double>(pairs);

  // Resident-only (reuse last uploaded pair): calc_device + warp.
  for (int i = 0; i < 4; ++i) {
    of.calc_device(d_prev, d_next, d_flow);
    of.warp_u8(d_prev, d_flow, d_mid, 0.5f);
  }
  of.finish();
  const auto r0 = std::chrono::steady_clock::now();
  constexpr int kIters = 20;
  for (int i = 0; i < kIters; ++i) {
    of.calc_device(d_prev, d_next, d_flow);
    of.warp_u8(d_prev, d_flow, d_mid, 0.5f);
  }
  of.finish();
  const auto r1 = std::chrono::steady_clock::now();
  const double resid_ms =
      std::chrono::duration<double, std::milli>(r1 - r0).count() / static_cast<double>(kIters);

  std::vector<std::uint8_t> mid(static_cast<std::size_t>(w) * h);
  of.download_u8(d_mid, mid.data(), mid.size());
  double mid_mean = 0.0;
  for (std::uint8_t v : mid)
    mid_mean += v;
  mid_mean /= static_cast<double>(mid.size());

  std::cout << "fruc_video_opencl " << w << "x" << h << " frames=" << n_frames
            << " pairs=" << pairs << " pipeline_H2D+calc+warp_ms=" << pipe_ms
            << " fps~=" << (1000.0 / pipe_ms) << " resident_calc+warp_ms=" << resid_ms
            << " fps~=" << (1000.0 / resid_ms) << " mid_mean_luma=" << mid_mean << "\n";
  return 0;
#endif
}
