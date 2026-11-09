// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Soft CI gate: SDK CPU DIS / Farneback / PyrLK GT-EPE on a textured synthetic
// shift, with OpenCV reference numbers printed. Not numerical identity vs
// OpenCV; Sintel/KITTI honest DIS disparity remains a lab gate.

#include "optical_flow_sdk/opencv_adapter.hpp"
#include "optical_flow_sdk/optical_flow.hpp"
#include "optical_flow_sdk/sparse_pyrlk.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

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

cv::Mat make_shifted(const cv::Mat &prev, float dx, float dy) {
  cv::Mat next(prev.size(), prev.type(), cv::Scalar(0));
  cv::Mat warp_map(prev.size(), CV_32FC2);
  for (int y = 0; y < prev.rows; ++y) {
    for (int x = 0; x < prev.cols; ++x)
      warp_map.at<cv::Vec2f>(y, x) =
          cv::Vec2f(static_cast<float>(x) - dx, static_cast<float>(y) - dy);
  }
  cv::remap(prev, next, warp_map, cv::noArray(), cv::INTER_LINEAR, cv::BORDER_CONSTANT);
  return next;
}

double mean_epe_vs_gt(const cv::Mat &flow, float dx, float dy, int border) {
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
  return n ? sum / n : 0.0;
}

} // namespace

int main() {
  using namespace optical_flow_sdk;

  constexpr int kW = 160;
  constexpr int kH = 120;
  constexpr float kDx = 2.0f;
  constexpr float kDy = -1.0f;

  const cv::Mat prev = make_textured(kW, kH);
  const cv::Mat next = make_shifted(prev, kDx, kDy);

  // DIS-lite vs OpenCV DIS-Fast
  {
    OpticalFlow of(Backend::Cpu, Preset::Fast, Algorithm::Dis);
    cv::Mat sdk_flow;
    opencv::calc(of, prev, next, sdk_flow);
    auto dis = cv::DISOpticalFlow::create(cv::DISOpticalFlow::PRESET_FAST);
    cv::Mat ocv_flow;
    dis->calc(prev, next, ocv_flow);
    const double sdk_epe = mean_epe_vs_gt(sdk_flow, kDx, kDy, 12);
    const double ocv_epe = mean_epe_vs_gt(ocv_flow, kDx, kDy, 12);
    std::cout << "dis_fast sdk_gt_epe=" << sdk_epe << " ocv_gt_epe=" << ocv_epe << "\n";
    if (sdk_epe > 2.5) {
      std::cerr << "DIS SDK GT-EPE too high\n";
      return EXIT_FAILURE;
    }
  }

  // Farneback vs OpenCV Farneback
  {
    OpticalFlow of(Backend::Cpu, Preset::Fast, Algorithm::Farneback);
    cv::Mat sdk_flow;
    opencv::calc(of, prev, next, sdk_flow);
    cv::Mat ocv_flow;
    cv::calcOpticalFlowFarneback(prev, next, ocv_flow, 0.5, 3, 15, 3, 5, 1.2, 0);
    const double sdk_epe = mean_epe_vs_gt(sdk_flow, kDx, kDy, 12);
    const double ocv_epe = mean_epe_vs_gt(ocv_flow, kDx, kDy, 12);
    std::cout << "farneback sdk_gt_epe=" << sdk_epe << " ocv_gt_epe=" << ocv_epe << "\n";
    if (sdk_epe > 2.0) {
      std::cerr << "Farneback SDK GT-EPE too high\n";
      return EXIT_FAILURE;
    }
  }

  // Sparse PyrLK vs OpenCV PyrLK
  {
    const std::vector<cv::Point2f> pts_cv = {{40.f, 30.f}, {80.f, 60.f}, {120.f, 90.f}};
    std::vector<Point2f> pts_sdk;
    for (const auto &p : pts_cv)
      pts_sdk.push_back({p.x, p.y});

    SparsePyrLKOptions opts;
    opts.max_level = 2;
    opts.win_size = 15;
    SparsePyrLK lk(opts);
    std::vector<Point2f> tracked;
    std::vector<std::uint8_t> status;
    std::vector<float> err;
    lk.calc(opencv::as_image_view(prev), opencv::as_image_view(next), pts_sdk, tracked, status, err);

    std::vector<cv::Point2f> next_cv;
    std::vector<std::uint8_t> status_cv;
    std::vector<float> err_cv;
    cv::calcOpticalFlowPyrLK(prev, next, pts_cv, next_cv, status_cv, err_cv,
                             cv::Size(opts.win_size, opts.win_size), opts.max_level);

    double sdk_epe = 0.0;
    double ocv_epe = 0.0;
    int ok = 0;
    for (std::size_t i = 0; i < pts_cv.size(); ++i) {
      if (!status[i] || !status_cv[i])
        continue;
      const double sdx = tracked[i].x - (pts_sdk[i].x + kDx);
      const double sdy = tracked[i].y - (pts_sdk[i].y + kDy);
      const double odx = next_cv[i].x - (pts_cv[i].x + kDx);
      const double ody = next_cv[i].y - (pts_cv[i].y + kDy);
      sdk_epe += std::sqrt(sdx * sdx + sdy * sdy);
      ocv_epe += std::sqrt(odx * odx + ody * ody);
      ++ok;
    }
    if (ok < 2) {
      std::cerr << "too few PyrLK tracks: " << ok << "\n";
      return EXIT_FAILURE;
    }
    sdk_epe /= ok;
    ocv_epe /= ok;
    std::cout << "pyrlk_sparse sdk_gt_epe=" << sdk_epe << " ocv_gt_epe=" << ocv_epe
              << " tracked=" << ok << "\n";
    if (sdk_epe > 1.0) {
      std::cerr << "PyrLK SDK GT-EPE too high\n";
      return EXIT_FAILURE;
    }
  }

  return EXIT_SUCCESS;
}
