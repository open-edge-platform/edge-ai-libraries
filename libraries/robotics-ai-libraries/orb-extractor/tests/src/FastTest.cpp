// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#ifndef OPENCV_FREE

#include <unistd.h>

#include <chrono>
#include <fstream>
#include <memory>

#include "TestUtil.h"
#include "gpu/gpu_kernels.h"
#include "gtest/gtest.h"
#include "orb_extractor.h"

#define EDGE_THRESHOLD 19
#define OVERLAP 6
#define WIDTHBLOCK 32

inline double getTimeStamp()
{
  namespace sc = std::chrono;
  sc::system_clock::duration d = sc::system_clock::now().time_since_epoch();
  sc::seconds s = sc::duration_cast<sc::seconds>(d);
  return s.count() + (sc::duration_cast<sc::microseconds>(d - s).count()) / 1e6;
}

using namespace cv;

template <typename pt>
struct cmp_pt
{
  bool operator()(const pt & a, const pt & b) const
  {
    return a.pt.y < b.pt.y || (a.pt.y == b.pt.y && a.pt.x < b.pt.x);
  }
};

void cpuFastExt(
  std::vector<cv::Mat> & input, std::vector<std::vector<cv::KeyPoint>> & raw_keypts, int num_levels,
  int ini_fast_thr_, int min_fast_thr_, bool nmsOn)
{
  const int max_num_keypts_ = 35000;
  const float cell_size = WIDTHBLOCK;
  const int overlap = OVERLAP;

  raw_keypts.resize(num_levels);

  for (unsigned int level = 0; level < num_levels; ++level) {
    constexpr unsigned int min_border_x = EDGE_THRESHOLD;
    constexpr unsigned int min_border_y = EDGE_THRESHOLD;
    const unsigned int max_border_x = input.at(level).cols - EDGE_THRESHOLD;
    const unsigned int max_border_y = input.at(level).rows - EDGE_THRESHOLD;

    const unsigned int width = max_border_x - min_border_x;
    const unsigned int height = max_border_y - min_border_y;

    const unsigned int num_cols = std::ceil(width / cell_size) + 1;
    const unsigned int num_rows = std::ceil(height / cell_size) + 1;

    std::vector<cv::KeyPoint> & keypts_to_distribute = raw_keypts.at(level);
    keypts_to_distribute.reserve(max_num_keypts_ * level);

    for (unsigned int i = 0; i < num_rows; ++i) {
      const unsigned int min_y = min_border_y + i * cell_size;
      if (max_border_y - overlap <= min_y) {
        continue;
      }
      unsigned int max_y = min_y + cell_size + overlap;
      if (max_border_y < max_y) {
        max_y = max_border_y;
      }
      for (unsigned int j = 0; j < num_cols; ++j) {
        const unsigned int min_x = min_border_x + j * cell_size;
        if (max_border_x - overlap <= min_x) {
          continue;
        }
        unsigned int max_x = min_x + cell_size + overlap;
        if (max_border_x < max_x) {
          max_x = max_border_x;
        }
        std::vector<cv::KeyPoint> keypts_in_cell;

        cv::FAST(
          input.at(level).rowRange(min_y, max_y).colRange(min_x, max_x), keypts_in_cell,
          ini_fast_thr_, nmsOn);

        // Re-compute FAST keypoint with reduced threshold if enough keypoint
        // was not got
        if (keypts_in_cell.empty()) {
          cv::FAST(
            input.at(level).rowRange(min_y, max_y).colRange(min_x, max_x), keypts_in_cell,
            min_fast_thr_, nmsOn);
        }
        if (keypts_in_cell.empty()) {
          continue;
        }

        // Collect keypoints for every scale
        {
          for (auto & keypt : keypts_in_cell) {
            keypt.pt.x += j * cell_size;
            keypt.pt.y += i * cell_size;
            keypts_to_distribute.push_back(keypt);
          }
        }
      }
    }
    std::sort(keypts_to_distribute.begin(), keypts_to_distribute.end(), cmp_pt<cv::KeyPoint>());
  }
}

bool compareKeyPoints(vector<cv::KeyPoint> & cpuKeypts, std::vector<gpu::PartKey> & gpuKeypts)
{
  if (cpuKeypts.size() != gpuKeypts.size()) {
    std::cout << "\n gpukeypts and cpukeypts are not same size\n";
    std::cout << "cpu keypoints size=" << cpuKeypts.size()
              << " gpu keypoints size=" << gpuKeypts.size() << "\n";
    return false;
  }

  for (int i = 0; i < gpuKeypts.size(); i++) {
    if (cpuKeypts[i].pt.x != gpuKeypts[i].pt.x && cpuKeypts[i].pt.y != gpuKeypts[i].pt.y) {
      std::cout << "\n gpukeypts and cpukeypts are not matching\n" << i << "\n";
      return false;
    }
  }
  return true;
}

void PartkeyToCVkey(std::vector<gpu::PartKey> & in_gpuKeypts, vector<cv::KeyPoint> & out_cvKeypts)
{
  for (int i = 0; i < in_gpuKeypts.size(); i++) {
    out_cvKeypts[i].pt.x = in_gpuKeypts[i].pt.x;
    out_cvKeypts[i].pt.y = in_gpuKeypts[i].pt.y;
  }
}

void fastTest(bool nmsOn)
{
  const auto width = 1920;
  const auto height = 1280;

  int total_level = 1;
  float scale_factor = 1.2;
  unsigned int num_levels = 8;
  unsigned int ini_fast_thr = 20;
  unsigned int min_fast_thr = 7;

  static constexpr unsigned int orb_patch_radius = 19;
  static constexpr unsigned int orb_overlap_size = 6;
  static constexpr unsigned int orb_cell_size = 32;

  static constexpr unsigned int min_border_x = orb_patch_radius;
  static constexpr unsigned int min_border_y = orb_patch_radius;

  std::vector<cv::Mat> src(1);
  std::vector<cv::Mat> gpusrc(total_level);
  cv::Mat src2;
  cv::Size sz(width, height);

  src2 = cv::imread(DATAPATH + "/market.jpg", IMREAD_GRAYSCALE);
  cv::resize(src2, src.at(0), sz, cv::INTER_LINEAR);

  cv::resize(src2, gpusrc.at(0), sz, cv::INTER_LINEAR);

  auto orbKernel = std::make_shared<gpu::ORBKernel>();

  orbKernel->setMaxkeypts(250000);

  gpu::Image8u srcImg;
  srcImg.resize(src.at(0).rows, src.at(0).cols);
  srcImg.upload(src.at(0).data);

  gpu::Image8u maskImg;
  bool mask_check = false;

  std::vector<gpu::PartKey> gpuKeypts;

  orbKernel->fastExt(
    srcImg, maskImg, mask_check, ini_fast_thr, min_fast_thr, orb_patch_radius, orb_overlap_size,
    orb_cell_size, 1, 0, nmsOn);
  orbKernel->downloadKeypoints(gpuKeypts, 0);

  // sort gpuKeypts
  std::sort(gpuKeypts.begin(), gpuKeypts.end(), cmp_pt<gpu::PartKey>());

  vector<vector<cv::KeyPoint>> cpuKeypts;

  // call cpufastExt
  cpuFastExt(gpusrc, cpuKeypts, total_level, ini_fast_thr, min_fast_thr, nmsOn);

  // compare GPU and CPU result
  ASSERT_TRUE(compareKeyPoints(cpuKeypts[0], gpuKeypts));
}

TEST(FastTest, Positive) { fastTest(false); }

TEST(FastTest_WithNMS, Positive) { fastTest(true); }

#endif  // OPENCV_FREE
