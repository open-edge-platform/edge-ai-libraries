// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include "orb_extractor.h"
#include "gpu/gpu_kernels.h"
#include "gpu/kernel_base.h"
#include "gpu/device_image.h"
#include "orb_point_pairs.h"
#include "gtest/gtest.h"
#include "TestUtil.h"
#include <opencv2/core/mat.hpp>
#include <opencv2/core/types.hpp>

using namespace cv;

int descriImgsize = 32;

void orbDescTest()
{
    cv::Mat src;
    cv::Mat resize_dst;
    cv::Size sz(640,480);

    src = cv::imread(DATAPATH+"/market.jpg", cv::IMREAD_GRAYSCALE);
    cv::resize(src, resize_dst, std::move(sz), 0, 0, cv::INTER_LINEAR);

    //pattern computation umax buffer
    ///////////////////////////////////////////////////////////////////
    constexpr int N = 256 * 4;
    static int bit_pattern[N];
    std::vector<cv::Point> pattern;
    const int npoints = 512;

    std::copy(orb_point_pairs, orb_point_pairs+N, bit_pattern);

    const cv::Point * pattern0 = (const cv::Point*)bit_pattern;
    std::copy(pattern0, pattern0 + npoints, std::back_inserter(pattern));

    /////////////////////////////////////////////////////////////////////
    // This is for orientation
    // pre-compute the end of a row in a circular patch
    std::vector<int> umax;
    umax.resize(HALF_PATCH_SIZE + 1);

    int v, v0, vmax = cvFloor(HALF_PATCH_SIZE * sqrt(2.f) / 2 + 1);
    int vmin = cvCeil(HALF_PATCH_SIZE * sqrt(2.f) / 2);
    const double hp2 = HALF_PATCH_SIZE*HALF_PATCH_SIZE;
    for (v = 0; v <= vmax; ++v)
        umax[v] = cvRound(sqrt(hp2 - v * v));

    // Make sure we are symmetric
    for (v = HALF_PATCH_SIZE, v0 = 0; v >= vmin; --v)
    {
        while (umax[v0] == umax[v0 + 1])
            ++v0;
        umax[v] = v0;
        ++v0;
    }
    ////////////////////////////////////////////////////////////////////

    //detect keypoint using fast
    ////////////////////////////////////////////////////////////////////
    vector<cv::KeyPoint> vKeypoint;
    vector<cv::KeyPoint> fltrvKeypoint;

    cv::FAST(resize_dst, vKeypoint, 20, true);

    for(auto& keypoint : vKeypoint)
    {
        if( keypoint.pt.x > 19 && keypoint.pt.y > 19 && keypoint.pt.x < 618  && keypoint.pt.y < 455  )
        {
            fltrvKeypoint.push_back(keypoint);
        }
    }
    int nkeypoints = fltrvKeypoint.size();

    /////////////////////////////////////////////////////////////////////////////
    //CPU
    cv::Mat cpuDescriptors;

    cpuDescriptors.create(nkeypoints, descriImgsize, CV_8UC1);

    cv::Mat gaussianImg;
    cv::GaussianBlur(resize_dst, gaussianImg, cv::Size(7,7), 2, 2, cv::BORDER_REPLICATE);

    computeOrientation(resize_dst, fltrvKeypoint, umax);

    orbDescCPU(gaussianImg, fltrvKeypoint, cpuDescriptors, pattern, descriImgsize );
    ///////////////////////////////////////////////////////////////////////////////////////////////

    //GPU
    //set keypts
    std::vector<gpu::PartKey> keypts(nkeypoints);
    int i = 0;
    for (vector<cv::KeyPoint>::iterator keypoint = fltrvKeypoint.begin(),
            keypointEnd = fltrvKeypoint.end(); keypoint != keypointEnd; ++keypoint)
    {
        keypts[i].pt.x = keypoint->pt.x;
        keypts[i].pt.y = keypoint->pt.y;
        keypts[i].response = keypoint->response;
        i++;
    }

    auto orbKernel = std::make_shared<gpu::ORBKernel>();
    auto device_base = orbKernel->getDeviceBase();

    orbKernel->setKernelPath(ORBLZE_KERNEL_PATH_STRING);

    gpu::Image8u gaussImg;
    gaussImg.setDeviceBase(device_base);

    gaussImg.resize(gaussianImg.cols, gaussianImg.rows);
    gaussImg.upload(gaussianImg.data, gpu::kImmediate);

    gpu::Vec8u srcBuf;
    srcBuf.setDeviceBase(device_base);
    srcBuf.resize(resize_dst.cols, resize_dst.rows);
    srcBuf.upload(resize_dst.data, gpu::kImmediate);

    gpu::Vec32i umax_buf;
    umax_buf.setDeviceBase(device_base);
    umax_buf.resize(umax.size());
    umax_buf.upload(&umax[0], gpu::kImmediate);

    gpu::Vec32f pattern_buffer;
    pattern_buffer.setDeviceBase(device_base);
    pattern_buffer.resize(256 * 4);
    pattern_buffer.upload(&orb_point_pairs, gpu::kImmediate);

    int max_num_keypts = keypts.size();
    int patch_size = HALF_PATCH_SIZE;

    cv::Mat gpuDescriptors;
    gpuDescriptors.create(nkeypoints, descriImgsize, CV_8UC1);

    std::vector<cv::KeyPoint> dst_keypts;

    orbKernel->initializeGPU(keypts.size());
    orbKernel->orbDescriptor(keypts, srcBuf, gaussImg, pattern_buffer, umax_buf, dst_keypts, 0, patch_size, gpuDescriptors, 0, max_num_keypts);
    orbKernel->execute(gpu::kCmdList1);

    ASSERT_TRUE(cmp8U(gpuDescriptors.data, cpuDescriptors.data, nkeypoints*descriImgsize, 1));
}

TEST(OrbDescriptorTest, Positive)
{
    orbDescTest();
}
