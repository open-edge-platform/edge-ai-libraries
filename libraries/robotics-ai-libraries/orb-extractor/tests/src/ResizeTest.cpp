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



const float scalingOption[] = {0.5, 0.6, 1.2, 1.4, 1.65, 2.23};

void ResizeOpenCV(cv::Mat& src, cv::Mat& dst, float scale, cv::InterpolationFlags inter)
{
    auto dstWidth = src.cols * scale;
    auto dstHeight = src.rows * scale;
    cv::resize(src, dst, cv::Size(dstWidth, dstHeight), 0, 0, inter);
}

void resizeTest(gpu::InterpolationType interType, cv::InterpolationFlags cvInter, int datatype)
{
    const auto width = 1920;
    const auto height = 1280;
    int size[] = {height, width};
    cv::Mat src, dst;

    readTestInput(src, DATAPATH+"/market.jpg", size, 2, CV_8UC1);

    auto orbKernel = std::make_shared<gpu::ORBKernel>();
    auto device_base = orbKernel->getDeviceBase();

    orbKernel->setKernelPath(ORBLZE_KERNEL_PATH_STRING);

    gpu::Vec8u srcImg;
    srcImg.setDeviceBase(device_base);

    srcImg.resize(src.cols, src.rows);
    srcImg.upload(src.data, gpu::kImmediate);

    for (int subi = 0; subi < sizeof(scalingOption)/sizeof(scalingOption[0]); subi++)
    {
        cout <<"scaling ratio =" << scalingOption[subi] << endl;

        int dstWidth = src.cols * scalingOption[subi];
        int dstHeight = src.rows * scalingOption[subi];
        gpu::Vec8u dstImg;
        dstImg.setDeviceBase(device_base);

        dstImg.resize(dstWidth, dstHeight);

        double fx = (double) dstWidth / width;
        double fy = (double) dstHeight / height;

        orbKernel->resize(srcImg, dstImg, interType, fx, fy);
        orbKernel->execute(gpu::kCmdList0);

        const cv::Size sz(dstWidth, dstHeight);
        auto dst = cv::Mat(sz, CV_8UC1);
        dstImg.download(dst.data, gpu::kImmediate);

        cv::Mat udst;
        ResizeOpenCV(src, udst, scalingOption[subi], cvInter);
        uchar* pCVDst = udst.data;
        uchar* pDst = dst.data;

        for (int ss = 0; ss < dstHeight; ss++)
        {
            for (int tt = 0; tt < dstWidth; tt++)
            {
		        if (abs(pDst[tt] - pCVDst[tt]) > 1)
                {
                    std::cout << "Failed at scaling option="<< scalingOption[subi];
                    std::cout << " at row="<< ss << " col=" << tt << std::endl;
                    std::cout << "pDst="<< (int)pDst[tt] << std::endl;
                    std::cout << "pCVDst="<< (int)pCVDst[tt] << std::endl;
                    std::cout << std::endl;
                    ASSERT_TRUE(false);
                }
		    }

            pDst += dstWidth;
            pCVDst += dstWidth;
        }
    }
}

TEST(ResizeLinearA8Test, Positive)
{
    resizeTest(gpu::kInterpolationLinear, cv::INTER_LINEAR, CV_8UC1);
}
