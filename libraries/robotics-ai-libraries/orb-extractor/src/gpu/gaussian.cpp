// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "gaussian.h"

namespace gpu
{

//cv::Mat coeffs = cv::getGaussianKernel(7, 2, CV_32F);
float coeffs[7] = {0.070159323513507843017578125, 0.1310748755931854248046875,
                   0.19071282446384429931640625, 0.216105937957763671875,
                   0.19071282446384429931640625, 0.1310748755931854248046875,
                   0.070159323513507843017578125};

void GaussianBlur::CreateKernel(Image8u &src_image, Image8u &dst_image,
        const double sigma)
{
    constexpr int width_block = 16;  // Need to match with kernel
    constexpr int height_block = 16; // Need to match with kernel

    const auto src_width = src_image.width();
    const auto src_height = src_image.height();
    auto dst_width = dst_image.width();
    auto dst_height = dst_image.height();

    if ((dst_width == 0) || (dst_height == 0))
    {
        dst_image.resize(src_width, src_height);
    }

    LoadKernel("gaussian_genx.bin", "gaussian_7x7_GENX");
    SetCommandListIndex(cmdlist_);
    //TODO:  Add check for dst_width/height with src

    uint32_t gridx = divUp(src_width, width_block);
    uint32_t gridy = divUp(src_height, height_block);

    SetGroupCount(gridx, gridy, 1);

    auto src = src_image.raw();
    auto dst = dst_image.raw();

    SetArgs<decltype(src)>(&src);
    SetArgs<decltype(src)>(&dst);
    SetArgs<decltype(coeffs)>(&coeffs);
}


void GaussianBlur::Submit()
{
    SubmitKernel(GetKernelType());
}

} //namespace gpu
