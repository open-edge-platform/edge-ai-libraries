// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#ifndef OPENCV_FREE

#include "TestUtil.h"
#include "gpu/gpu_kernels.h"
#include "gtest/gtest.h"
#include "orb_extractor.h"

void GaussianTest(int kernelSize, cv::BorderTypes cvBorder, gpu::BorderTypes gpuBorder)
{
  float sigma = 2;
  cv::Mat src;

  src = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);

  int framesize = src.cols * src.rows;

  auto orbKernel = std::make_shared<gpu::ORBKernel>();

  gpu::Image8u srcImg, dstImg;

  srcImg.resize(src.rows, src.cols);
  srcImg.upload(src.data);
  dstImg.resize(src.rows, src.cols);

  orbKernel->gaussianBlur(srcImg, dstImg, kernelSize, gpuBorder);

  /*
 {
  float sigma = 2;
  const auto width = 707;
  const auto height = 400;
  int framesize = width * height;
  int size[] = {height, width};
  cv::Mat src;

  readTestInput(src, DATAPATH+"/market.jpg", size, 2, CV_8UC1);

  //auto orbKernel = std::make_shared<gpu::ORBKernel>();

  gpu::Image8u srcImg, dstImg;

  srcImg.resize(src.rows, src.cols);
  srcImg.upload(src.data);
  dstImg.resize(src.rows, src.cols);

  orbKernel->gaussianBlur(srcImg, dstImg, kernelSize, gpuBorder);
 }
 */

  const cv::Size sz(src.cols, src.rows);
  auto dst = cv::Mat(sz, CV_8UC1);
  dstImg.download(dst.data, dst.cols, dst.cols, dst.rows);

  cv::Mat cv_dst;
  cv::GaussianBlur(src, cv_dst, cv::Size(kernelSize, kernelSize), sigma, sigma, cvBorder);

  //    cv::Mat cv_dst2 = cv_dst.getMat(cv::ACCESS_READ);

  ASSERT_TRUE(cmp8U(dst.data, cv_dst.data, framesize, 5));
}

TEST(GaussianBlurTests_Border_Constant, Positive)
{
  GaussianTest(7, cv::BORDER_CONSTANT, gpu::BORDER_CONSTANT);
}

TEST(GaussianBlurTests_Border_Replicate, Positive)
{
  GaussianTest(7, cv::BORDER_REPLICATE, gpu::BORDER_REPLICATE);
}

TEST(GaussianBlurTests_Border_Reflect, Positive)
{
  GaussianTest(7, cv::BORDER_REFLECT, gpu::BORDER_REFLECT);
}

TEST(GaussianBlurTests_Border_Reflect_101, Positive)
{
  GaussianTest(7, cv::BORDER_REFLECT_101, gpu::BORDER_REFLECT_101);
}

#endif  // OPENCV_FREE
