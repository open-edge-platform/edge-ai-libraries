// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __GAUSSIAN_H__
#define __GAUSSIAN_H__

#include "kernel_base.h"

namespace gpu
{

static CommandListIndex g_gaussian_cmdlist;

class GaussianBlur : public KernelBase
{
public:

    using Ptr = std::shared_ptr<GaussianBlur>;

    static Ptr New(CommandListIndex index, CmBase::Ptr gpuObj)
    {
        g_gaussian_cmdlist = index;
        return std::make_shared<GaussianBlur>(gpuObj);
    }

    GaussianBlur(CmBase::Ptr gpuObj) : KernelBase(kGaussian, std::move(gpuObj))
    {
        cmdlist_ = g_gaussian_cmdlist;
    }

    ~GaussianBlur() {}

    void CreateKernel(Image8u &src_image, Image8u &dst_image,
            const double sigma);

    void Submit();

private:

    CommandListIndex cmdlist_;
};

} // namespace gpu

#endif // !__GAUSSIAN_H__



