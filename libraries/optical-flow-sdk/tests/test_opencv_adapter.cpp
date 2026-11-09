// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/opencv_adapter.hpp"
#include "optical_flow_sdk/optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <opencv2/core.hpp>

int main() {
  using namespace optical_flow_sdk;

  cv::Mat prev(48, 64, CV_8UC1);
  cv::Mat next(48, 64, CV_8UC1);
  for (int y = 0; y < prev.rows; ++y) {
    for (int x = 0; x < prev.cols; ++x) {
      const float v = 128.0f + 50.0f * std::sin(0.2f * x) * std::cos(0.15f * y);
      prev.at<std::uint8_t>(y, x) = static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  // Translate +2 px in x into next.
  next.setTo(0);
  prev(cv::Rect(0, 0, prev.cols - 2, prev.rows)).copyTo(next(cv::Rect(2, 0, prev.cols - 2, prev.rows)));

  OpticalFlow of(Backend::Cpu, Preset::Fast);
  cv::Mat flow;
  cv::Mat cost;
  opencv::calc(of, prev, next, flow, cost);
  if (flow.type() != CV_32FC2 || cost.type() != CV_8UC1) {
    std::cerr << "unexpected Mat types\n";
    return EXIT_FAILURE;
  }

  FlowField roundtrip = opencv::to_flow_field(flow);
  cv::Mat again = opencv::to_mat(roundtrip);
  if (cv::norm(flow, again, cv::NORM_INF) > 0.0) {
    std::cerr << "flow Mat roundtrip mismatch\n";
    return EXIT_FAILURE;
  }

  double sum = 0.0;
  int n = 0;
  for (int y = 8; y < flow.rows - 8; ++y) {
    for (int x = 8; x < flow.cols - 8; ++x) {
      const cv::Vec2f f = flow.at<cv::Vec2f>(y, x);
      const double eu = f[0] - 2.0;
      const double ev = f[1] - 0.0;
      sum += std::sqrt(eu * eu + ev * ev);
      ++n;
    }
  }
  const double epe = sum / n;
  std::cout << "opencv adapter synthetic EPE=" << epe << "\n";
  if (epe > 1.0) {
    std::cerr << "adapter path EPE too high\n";
    return EXIT_FAILURE;
  }
  return EXIT_SUCCESS;
}
