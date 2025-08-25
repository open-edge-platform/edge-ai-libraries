// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "resize.h"

namespace gpu
{

void Resize::CreateKernel(Vec8u &src_image, Vec8u &dst_image, const double fx,
        const double fy, const InterpolationType inter)
{
    constexpr int width_block = 16;  // Need to match with kernel
    constexpr int height_block = 8; // Need to match with kernel

    const auto src_width = src_image.width();
    const auto src_height = src_image.height();
    auto dst_width = dst_image.width();
    auto dst_height = dst_image.height();

    if (src_width == 0 || src_height == 0 || dst_width == 0 || dst_height == 0) {
        throw("Invalid image buffer size");
    }

    if (src_image.channel() == 1)
    {
        switch (inter)
        {
        case kInterpolationLinear:
            LoadKernel("resize_genx.bin", "resize_linear_A8_GENX");
            break;
        case kInterpolationNearest:
        case kInterpolationCubic:
        default:
            throw("Not implemented!!");
        }
    }
    else if (src_image.channel() == 4)
    {
        switch (inter)
        {
        case kInterpolationLinear:
        case kInterpolationNearest:
        case kInterpolationCubic:
        default:
            throw("Not implemented!!");
        }
    }

    uint32_t gridx = divUp(dst_width, width_block);
    uint32_t gridy = divUp(dst_height, height_block);

    SetGroupCount(gridx, gridy, 1);
    SetCommandListIndex(cmdlist_);

    float inv_fx = 0.f, inv_fy = 0.f;

    if ((fx == 0.0) || (fy == 0.0))
    {
        double scale_x = (double) dst_width / src_width;
        double scale_y = (double) dst_height / src_height;

        inv_fx = 1.0f / (float) scale_x;
        inv_fy = 1.0f / (float) scale_y;
    }
    else
    {
        inv_fx = 1.0f / (float) fx;
        inv_fy = 1.0f / (float) fy;
    }

    auto src = src_image.raw();
    auto dst = dst_image.raw();

    SetArgs<decltype(src)>(&src);
    SetArgs<decltype(dst)>(&dst);
    SetArgs<decltype(src_width)>(&src_width);
    SetArgs<decltype(src_height)>(&src_height);
    SetArgs<decltype(dst_width)>(&dst_width);
    SetArgs<decltype(inv_fx)>(&inv_fx);
    SetArgs<decltype(inv_fy)>(&inv_fy);

}

void Resize::Submit()
{
    SubmitKernel(GetKernelType());
}

} //namespace gpu
