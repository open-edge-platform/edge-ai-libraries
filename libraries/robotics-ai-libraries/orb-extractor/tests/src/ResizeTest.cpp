// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0
//
#include <opencv2/opencv.hpp>

#include "TestUtil.h"
#include "gpu/gpu_kernels.h"
#include "gtest/gtest.h"
#include "orb_extractor.h"

const float scalingOption[] = {0.5, 0.6, 1.2, 1.4, 1.65, 2.23};

void ResizeOpenCV(cv::Mat & src, cv::UMat & dst, float scale, cv::InterpolationFlags inter)
{
  auto dstWidth = src.cols * scale;
  auto dstHeight = src.rows * scale;
  cv::resize(src, dst, cv::Size(dstWidth, dstHeight), 0, 0, inter);
}

void resizeTest(gpu::InterpolationType interType, cv::InterpolationFlags cvInter, int datatype)
{
  cv::Mat src;
  cv::UMat dst;

  src = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);

  auto orbKernel = std::make_shared<gpu::ORBKernel>();

  gpu::Image8u srcImg;

  srcImg.resize(src.rows, src.cols);
  srcImg.upload(src.data);

  for (int subi = 0; subi < sizeof(scalingOption) / sizeof(scalingOption[0]); subi++) {
    std::cout << "scaling ratio =" << scalingOption[subi] << std::endl;

    int dstWidth = src.cols * scalingOption[subi];
    int dstHeight = src.rows * scalingOption[subi];
    gpu::Image8u dstImg;

    dstImg.resize(dstHeight, dstWidth);

    orbKernel->resize(srcImg, dstImg, interType, 0.0, 0.0);

    const cv::Size sz(dstImg.cols(), dstImg.rows());
    auto gpuDst = cv::Mat(sz, CV_8UC1);
    dstImg.download(gpuDst.data, gpuDst.cols, gpuDst.cols, gpuDst.rows);

    ResizeOpenCV(src, dst, scalingOption[subi], cvInter);

    cv::Mat m = dst.getMat(cv::ACCESS_READ);
    uchar * pCVDst = m.data;
    uchar * pDst = gpuDst.data;

    for (int ss = 0; ss < dst.rows; ss++) {
      for (int tt = 0; tt < dst.cols; tt++) {
        if (pDst[tt] != pCVDst[tt]) {
          std::cout << "Failed at scaling option=" << scalingOption[subi];
          std::cout << " at row=" << ss << " col=" << tt << std::endl;
          std::cout << "pDst=" << (int)pDst[tt] << std::endl;
          std::cout << "pCVDst=" << (int)pCVDst[tt] << std::endl;
          std::cout << std::endl;
          ASSERT_TRUE(false);
        }
      }

      pDst += dst.cols;
      pCVDst += dst.cols;
    }
  }
}

TEST(ResizeLinearA8Test, Positive)
{
  // Using SYCL GPU acceleration, no OpenCL check needed
  resizeTest(gpu::kInterpolationLinear, cv::INTER_LINEAR, CV_8UC1);
}

TEST(ResizeNearestA8Test, Positive)
{
  // Using SYCL GPU acceleration, no OpenCL check needed
  resizeTest(gpu::kInterpolationNearest, cv::INTER_NEAREST, CV_8UC1);
}
