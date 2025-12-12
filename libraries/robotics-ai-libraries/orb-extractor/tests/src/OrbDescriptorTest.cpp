// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0
//
#include <opencv2/core/mat.hpp>
#include <opencv2/core/types.hpp>

#include "TestUtil.h"
#include "gpu/gpu_kernels.h"
#include "gtest/gtest.h"
#include "orb_extractor.h"
#include "orb_point_pairs.h"

using namespace cv;

int descriImgsize = 32;

#include <chrono>
inline double getTimeStamp()
{
  std::chrono::system_clock::duration d = std::chrono::system_clock::now().time_since_epoch();
  std::chrono::seconds s = std::chrono::duration_cast<std::chrono::seconds>(d);
  return s.count() + (std::chrono::duration_cast<std::chrono::microseconds>(d - s).count()) / 1e6;
}

void orbDescTest()
{
  cv::Mat src;
  cv::Mat resize_dst;
  float scale_factor = 1.0f;
  // cv::Size sz(640, 480);
  cv::Size sz(1920, 1280);

  src = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);
  cv::resize(src, resize_dst, sz, 0, 0, cv::INTER_LINEAR);

  // pattern computation umax buffer
  ///////////////////////////////////////////////////////////////////
  constexpr int N = 256 * 4;
  static int bit_pattern[N];
  std::vector<cv::Point> pattern;
  const int npoints = 512;

  std::copy(orb_point_pairs, orb_point_pairs + N, bit_pattern);

  const cv::Point * pattern0 = (const cv::Point *)bit_pattern;
  std::copy(pattern0, pattern0 + npoints, std::back_inserter(pattern));

  /////////////////////////////////////////////////////////////////////
  // This is for orientation
  // pre-compute the end of a row in a circular patch
  std::vector<int> umax;
  umax.resize(HALF_PATCH_SIZE + 1);

  int v, v0, vmax = cvFloor(HALF_PATCH_SIZE * sqrt(2.f) / 2 + 1);
  int vmin = cvCeil(HALF_PATCH_SIZE * sqrt(2.f) / 2);
  const double hp2 = HALF_PATCH_SIZE * HALF_PATCH_SIZE;
  for (v = 0; v <= vmax; ++v) umax[v] = cvRound(sqrt(hp2 - v * v));

  // Make sure we are symmetric
  for (v = HALF_PATCH_SIZE, v0 = 0; v >= vmin; --v) {
    while (umax[v0] == umax[v0 + 1]) ++v0;
    umax[v] = v0;
    ++v0;
  }
  ////////////////////////////////////////////////////////////////////

  // detect keypoint using fast
  ////////////////////////////////////////////////////////////////////
  vector<cv::KeyPoint> vKeypoint;
  vector<cv::KeyPoint> fltrvKeypoint;

  cv::FAST(resize_dst, vKeypoint, 20, true);

  for (auto & keypoint : vKeypoint) {
    if (
      keypoint.pt.x > 19 && keypoint.pt.y > 19 && keypoint.pt.x < resize_dst.cols - 19 &&
      keypoint.pt.y < resize_dst.rows - 19) {
      fltrvKeypoint.push_back(keypoint);
    }
  }
  int nkeypoints = fltrvKeypoint.size();

  std::cout << "keypoint size=" << nkeypoints << "\n";

  /////////////////////////////////////////////////////////////////////////////
  // CPU
  cv::Mat cpuDescriptors;

  cpuDescriptors.create(nkeypoints, descriImgsize, CV_8UC1);

  cv::Mat gaussianImg;
  cv::GaussianBlur(resize_dst, gaussianImg, cv::Size(7, 7), 2, 2, cv::BORDER_REPLICATE);

  computeOrientation(resize_dst, fltrvKeypoint, umax);

  orbDescCPU(gaussianImg, fltrvKeypoint, cpuDescriptors, pattern, descriImgsize);
  ///////////////////////////////////////////////////////////////////////////////////////////////

  // GPU
  // set keypts
  std::vector<gpu::PartKey> keypts(nkeypoints);
  int i = 0;
  for (vector<cv::KeyPoint>::iterator keypoint = fltrvKeypoint.begin(),
                                      keypointEnd = fltrvKeypoint.end();
       keypoint != keypointEnd; ++keypoint) {
    keypts[i].pt.x = keypoint->pt.x;
    keypts[i].pt.y = keypoint->pt.y;
    keypts[i].response = keypoint->response;
    i++;
  }

  auto orbKernel = std::make_shared<gpu::ORBKernel>();

  gpu::Image8u gaussImg;

  gaussImg.resize(gaussianImg.rows, gaussianImg.cols);
  gaussImg.upload(gaussianImg.data);

  gpu::Image8u srcImg;
  srcImg.resize(resize_dst.rows, resize_dst.cols);
  srcImg.upload(resize_dst.data);

  gpu::Vec32i umax_buf;
  umax_buf.resize(umax.size());
  umax_buf.upload(&umax[0], umax.size());

  gpu::Vec32f pattern_buffer;
  pattern_buffer.resize(256 * 4);
  pattern_buffer.upload(&orb_point_pairs[0], 256 * 4);

  int max_num_keypts = keypts.size();
  int patch_size = HALF_PATCH_SIZE / 2;

  cv::Mat gpuDescriptors2;
  gpuDescriptors2.create(nkeypoints, descriImgsize, CV_8UC1);

  std::vector<cv::KeyPoint> dst_keypts2;
  orbKernel->orbDescriptor(keypts, srcImg, gaussImg, pattern_buffer, umax_buf, 0);

  orbKernel->downloadKeypointsDescriptors(
    dst_keypts2, gpuDescriptors2, 0, 0, patch_size, scale_factor);

  cv::Mat gpuDescriptors;
  gpuDescriptors.create(nkeypoints, descriImgsize, CV_8UC1);

  double start = getTimeStamp();
  std::vector<cv::KeyPoint> dst_keypts;
  orbKernel->orbDescriptor(keypts, srcImg, gaussImg, pattern_buffer, umax_buf, 0);

  orbKernel->downloadKeypointsDescriptors(
    dst_keypts, gpuDescriptors, 0, 0, patch_size, scale_factor);

  double end = getTimeStamp();
  std::cout << "time for orb=" << (end - start) * 1000.0 << " ms\n";
  ASSERT_TRUE(cmp8U(gpuDescriptors.data, cpuDescriptors.data, nkeypoints * descriImgsize, 1));
}

TEST(OrbDescriptorTest, Positive) { orbDescTest(); }
