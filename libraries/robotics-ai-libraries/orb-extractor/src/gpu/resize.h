// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __RESIZE_H__
#define __RESIZE_H__

#include "kernel_base.h"

namespace gpu
{

static CommandListIndex g_resize_cmdlist;

class Resize : public KernelBase
{
public:

    using Ptr = std::shared_ptr<Resize>;

    static Ptr New(CommandListIndex index, CmBase::Ptr gpuObj)
    {
        g_resize_cmdlist = index;
        return std::make_shared<Resize>(gpuObj);
    }

    Resize(CmBase::Ptr gpuObj) : KernelBase(kResize, std::move(gpuObj))
    {
        cmdlist_ = g_resize_cmdlist;
    }

    ~Resize() { }

    void CreateKernel(Vec8u &src_image, Vec8u &dst_image, const double fx,
            const double fy, const InterpolationType inter);

    void Submit();

private:

    CommandListIndex cmdlist_;
};

} //namespace gpu

#endif // !__RESIZE_H__


