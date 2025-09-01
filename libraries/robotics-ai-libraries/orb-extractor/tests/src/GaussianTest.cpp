// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "orb_extractor.h"
#include "gpu/gpu_kernels.h"
#include "gpu/kernel_base.h"
#include "gpu/device_image.h"
#include "gtest/gtest.h"
#include "TestUtil.h"
#include <opencv2/core/mat.hpp>
#include <opencv2/core/types.hpp>


class GaussianTest : public ::testing::TestWithParam<int>
{
};

TEST_P(GaussianTest, Positive)
{
    float sigma = 2;
    const auto width = 1920;
    const auto height = 1280;
    int framesize = width * height;
    int size[] = {height, width};
    cv::Mat src;
    int kernelSize =  GetParam();

    readTestInput(src, DATAPATH+"/market.jpg", size, 2, CV_8UC1);

    gpu::Image8u srcImg, dstImg;

    auto orbKernel = std::make_shared<gpu::ORBKernel>();
    auto device_base = orbKernel->getDeviceBase();

    orbKernel->setKernelPath(ORBLZE_KERNEL_PATH_STRING);

    srcImg.setDeviceBase(device_base);
    dstImg.setDeviceBase(device_base);

    srcImg.resize(src.cols, src.rows);
    srcImg.upload(src.data, gpu::kImmediate);
    dstImg.resize(src.cols, src.rows);

    orbKernel->gaussianBlur(srcImg, dstImg, kernelSize, 2);
    orbKernel->execute(gpu::kCmdList0);

    const cv::Size sz(src.cols, src.rows);
    auto dst = cv::Mat(sz, CV_8UC1);
    dstImg.download(dst.data, gpu::kImmediate);
    cv::Mat cv_dst;
    cv::GaussianBlur(src, cv_dst, cv::Size(kernelSize, kernelSize), sigma, sigma, cv::BORDER_REPLICATE);

    ASSERT_TRUE(cmp8U(dst.data , cv_dst.data, framesize, 5));
}

INSTANTIATE_TEST_SUITE_P(GaussianPositiveTests, GaussianTest, testing::Values(7));

