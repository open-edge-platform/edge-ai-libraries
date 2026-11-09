// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// CPU OpenCV parity diagnostic (not a hard Sintel/KITTI gate): report EPE vs
// known synthetic shift and pairwise EPE vs OpenCV for DIS, Farneback, and
// sparse PyrLK. Full dataset parity remains a lab gate.

#include "optical_flow_sdk/opencv_adapter.hpp"
#include "optical_flow_sdk/optical_flow.hpp"
#include "optical_flow_sdk/sparse_pyrlk.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <string>
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

double mean_epe_pairwise(const cv::Mat &a, const cv::Mat &b, int border) {
  double sum = 0.0;
  int n = 0;
  for (int y = border; y < a.rows - border; ++y) {
    for (int x = border; x < a.cols - border; ++x) {
      const cv::Vec2f fa = a.at<cv::Vec2f>(y, x);
      const cv::Vec2f fb = b.at<cv::Vec2f>(y, x);
      const double eu = fa[0] - fb[0];
      const double ev = fa[1] - fb[1];
      sum += std::sqrt(eu * eu + ev * ev);
      ++n;
    }
  }
  return n ? sum / n : 0.0;
}

double ms_since(std::chrono::steady_clock::time_point t0,
                std::chrono::steady_clock::time_point t1) {
  return std::chrono::duration<double, std::milli>(t1 - t0).count();
}

struct DenseRow {
  const char *name;
  double sdk_epe = 0.0;
  double ocv_epe = 0.0;
  double pair_epe = 0.0;
  double sdk_ms = 0.0;
  double ocv_ms = 0.0;
};

DenseRow run_dense(const char *name, optical_flow_sdk::OpticalFlow &of, cv::Mat &ocv_flow_out,
                   const cv::Mat &prev, const cv::Mat &next, float dx, float dy,
                   const std::function<void(const cv::Mat &, const cv::Mat &, cv::Mat &)> &ocv_calc) {
  DenseRow row;
  row.name = name;
  cv::Mat sdk_flow;
  const auto t0 = std::chrono::steady_clock::now();
  optical_flow_sdk::opencv::calc(of, prev, next, sdk_flow);
  const auto t1 = std::chrono::steady_clock::now();
  ocv_calc(prev, next, ocv_flow_out);
  const auto t2 = std::chrono::steady_clock::now();
  row.sdk_epe = mean_epe_vs_gt(sdk_flow, dx, dy, 16);
  row.ocv_epe = mean_epe_vs_gt(ocv_flow_out, dx, dy, 16);
  row.pair_epe = mean_epe_pairwise(sdk_flow, ocv_flow_out, 16);
  row.sdk_ms = ms_since(t0, t1);
  row.ocv_ms = ms_since(t1, t2);
  return row;
}

} // namespace

int main(int argc, char **argv) {
  bool strict = false;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--strict")
      strict = true;
    else if (arg == "-h" || arg == "--help") {
      std::cout << "usage: compare_opencv_dis [--strict]\n"
                   "  Synthetic CPU parity vs OpenCV DIS / Farneback / PyrLK.\n"
                   "  --strict  fail if SDK GT-EPE exceeds soft CI ceilings\n";
      return 0;
    }
  }

  constexpr int kW = 320;
  constexpr int kH = 240;
  constexpr float kDx = 3.0f;
  constexpr float kDy = -2.0f;

  const cv::Mat prev = make_textured(kW, kH);
  const cv::Mat next = make_shifted(prev, kDx, kDy);

  std::cout << "synthetic " << kW << "x" << kH << " shift=(" << kDx << "," << kDy << ")\n"
            << "columns: name  sdk_gt_epe  ocv_gt_epe  pair_epe  sdk_ms  ocv_ms\n";

  std::vector<DenseRow> rows;

  {
    optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu, optical_flow_sdk::Preset::Fast,
                                     optical_flow_sdk::Algorithm::Dis);
    cv::Mat ocv;
    rows.push_back(run_dense(
        "dis_fast", of, ocv, prev, next, kDx, kDy, [](const cv::Mat &a, const cv::Mat &b, cv::Mat &out) {
          auto dis = cv::DISOpticalFlow::create(cv::DISOpticalFlow::PRESET_FAST);
          dis->calc(a, b, out);
        }));
  }
  {
    optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu, optical_flow_sdk::Preset::Fast,
                                     optical_flow_sdk::Algorithm::Farneback);
    cv::Mat ocv;
    rows.push_back(run_dense(
        "farneback", of, ocv, prev, next, kDx, kDy, [](const cv::Mat &a, const cv::Mat &b, cv::Mat &out) {
          cv::calcOpticalFlowFarneback(a, b, out, 0.5, 3, 15, 3, 5, 1.2, 0);
        }));
  }

  for (const DenseRow &r : rows) {
    std::cout << r.name << "  " << r.sdk_epe << "  " << r.ocv_epe << "  " << r.pair_epe << "  "
              << r.sdk_ms << "  " << r.ocv_ms << "\n";
  }

  // Sparse PyrLK: track a few known points; compare to OpenCV calcOpticalFlowPyrLK.
  {
    using optical_flow_sdk::Point2f;
    using optical_flow_sdk::SparsePyrLK;
    using optical_flow_sdk::SparsePyrLKOptions;

    const std::vector<cv::Point2f> pts_cv = {{64.f, 48.f}, {160.f, 120.f}, {240.f, 180.f}, {100.f, 200.f}};
    std::vector<Point2f> pts_sdk;
    pts_sdk.reserve(pts_cv.size());
    for (const auto &p : pts_cv)
      pts_sdk.push_back({p.x, p.y});

    SparsePyrLKOptions opts;
    opts.max_level = 2;
    opts.win_size = 21;
    SparsePyrLK lk(opts);
    std::vector<Point2f> tracked;
    std::vector<std::uint8_t> status;
    std::vector<float> err;
    const auto t0 = std::chrono::steady_clock::now();
    lk.calc(optical_flow_sdk::opencv::as_image_view(prev),
            optical_flow_sdk::opencv::as_image_view(next), pts_sdk, tracked, status, err);
    const auto t1 = std::chrono::steady_clock::now();

    std::vector<cv::Point2f> next_cv;
    std::vector<std::uint8_t> status_cv;
    std::vector<float> err_cv;
    cv::calcOpticalFlowPyrLK(prev, next, pts_cv, next_cv, status_cv, err_cv,
                             cv::Size(opts.win_size, opts.win_size), opts.max_level);
    const auto t2 = std::chrono::steady_clock::now();

    double sdk_epe = 0.0, ocv_epe = 0.0, pair = 0.0;
    int ok = 0;
    for (std::size_t i = 0; i < pts_cv.size(); ++i) {
      if (!status[i] || !status_cv[i])
        continue;
      const double sdx = tracked[i].x - (pts_sdk[i].x + kDx);
      const double sdy = tracked[i].y - (pts_sdk[i].y + kDy);
      const double odx = next_cv[i].x - (pts_cv[i].x + kDx);
      const double ody = next_cv[i].y - (pts_cv[i].y + kDy);
      const double pdx = tracked[i].x - next_cv[i].x;
      const double pdy = tracked[i].y - next_cv[i].y;
      sdk_epe += std::sqrt(sdx * sdx + sdy * sdy);
      ocv_epe += std::sqrt(odx * odx + ody * ody);
      pair += std::sqrt(pdx * pdx + pdy * pdy);
      ++ok;
    }
    if (ok > 0) {
      sdk_epe /= ok;
      ocv_epe /= ok;
      pair /= ok;
    }
    std::cout << "pyrlk_sparse  " << sdk_epe << "  " << ocv_epe << "  " << pair << "  "
              << ms_since(t0, t1) << "  " << ms_since(t1, t2) << "  tracked=" << ok << "/"
              << pts_cv.size() << "\n";

    if (strict) {
      if (ok < 3) {
        std::cerr << "strict: too few PyrLK tracks\n";
        return EXIT_FAILURE;
      }
      if (sdk_epe > 1.0) {
        std::cerr << "strict: PyrLK SDK GT-EPE too high\n";
        return EXIT_FAILURE;
      }
    }
  }

  std::cout << "note: SDK DIS is DIS-lite; dataset / honest OpenCV DIS parity is a lab gate\n";

  if (strict) {
    // Soft ceilings for synthetic textured shift — not OpenCV numerical identity.
    for (const DenseRow &r : rows) {
      const double ceiling = (std::string(r.name) == "dis_fast") ? 2.5 : 2.0;
      if (r.sdk_epe > ceiling) {
        std::cerr << "strict: " << r.name << " SDK GT-EPE " << r.sdk_epe << " > " << ceiling << "\n";
        return EXIT_FAILURE;
      }
    }
  }
  return EXIT_SUCCESS;
}
