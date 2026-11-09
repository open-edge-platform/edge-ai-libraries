// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Diagnostic (not a CI hard gate): report EPE of SDK CPU vs OpenCV DIS on a
// synthetic textured shift. Full Sintel/KITTI parity remains a lab gate.

#include "optical_flow_sdk/opencv_adapter.hpp"
#include "optical_flow_sdk/optical_flow.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/video/tracking.hpp>

namespace {

cv::Mat make_textured(int w, int h) {
  cv::Mat img(h, w, CV_8UC1);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const float v = 128.0f + 60.0f * std::sin(0.21f * x) * std::cos(0.17f * y) +
                      40.0f * std::sin(0.21f * x * 2.3f + 0.17f * y * 1.7f);
      img.at<std::uint8_t>(y, x) = static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  return img;
}

double mean_epe(const cv::Mat &flow, float dx, float dy, int border) {
  double sum = 0.0;
  int n = 0;
  for (int y = border; y < flow.rows - border; ++y) {
    for (int x = border; x < flow.cols - border; ++x) {
      const cv::Vec2f f = flow.at<cv::Vec2f>(y, x);
      const double eu = f[0] - dx;
      const double ev = f[1] - dy;
      sum += std::sqrt(eu * eu + ev * ev);
      ++n;
    }
  }
  return sum / n;
}

} // namespace

int main() {
  constexpr int kW = 320;
  constexpr int kH = 240;
  constexpr float kDx = 3.0f;
  constexpr float kDy = -2.0f;

  cv::Mat prev = make_textured(kW, kH);
  cv::Mat next(kH, kW, CV_8UC1, cv::Scalar(0));
  cv::Mat warp_map(kH, kW, CV_32FC2);
  for (int y = 0; y < kH; ++y) {
    for (int x = 0; x < kW; ++x)
      warp_map.at<cv::Vec2f>(y, x) = cv::Vec2f(static_cast<float>(x) - kDx, static_cast<float>(y) - kDy);
  }
  cv::remap(prev, next, warp_map, cv::noArray(), cv::INTER_LINEAR, cv::BORDER_CONSTANT);

  optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu, optical_flow_sdk::Preset::Fast);
  cv::Mat sdk_flow;
  const auto t0 = std::chrono::steady_clock::now();
  optical_flow_sdk::opencv::calc(of, prev, next, sdk_flow);
  const auto t1 = std::chrono::steady_clock::now();

  auto dis = cv::DISOpticalFlow::create(cv::DISOpticalFlow::PRESET_FAST);
  cv::Mat ocv_flow;
  const auto t2 = std::chrono::steady_clock::now();
  dis->calc(prev, next, ocv_flow);
  const auto t3 = std::chrono::steady_clock::now();

  const double sdk_epe = mean_epe(sdk_flow, kDx, kDy, 16);
  const double ocv_epe = mean_epe(ocv_flow, kDx, kDy, 16);
  const double ms_sdk = std::chrono::duration<double, std::milli>(t1 - t0).count();
  const double ms_ocv = std::chrono::duration<double, std::milli>(t3 - t2).count();

  std::cout << "synthetic " << kW << "x" << kH << " shift=(" << kDx << "," << kDy << ")\n"
            << "sdk_cpu  EPE=" << sdk_epe << "  wall_ms=" << ms_sdk << "\n"
            << "opencv_dis EPE=" << ocv_epe << "  wall_ms=" << ms_ocv << "\n"
            << "note: SDK CPU is DIS-lite; strict OpenCV parity is a lab/SYCL gate\n";
  return 0;
}
