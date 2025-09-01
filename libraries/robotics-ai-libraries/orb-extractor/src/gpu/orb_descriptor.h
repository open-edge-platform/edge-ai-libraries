// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __ORB_DESCRIPTOR_H__
#define __ORB_DESCRIPTOR_H__

#include "kernel_base.h"
#include "gpu_kernels.h"

namespace gpu
{

static CommandListIndex g_descriptor_command_list;
static uint32_t         g_max_keypoints;

class OrbDescriptor : public KernelBase
{
public:

    using Ptr = std::shared_ptr<OrbDescriptor>;

    static Ptr New(CommandListIndex index, uint32_t max_output_keypoints, CmBase::Ptr gpuObj)
    {
        g_descriptor_command_list = index;
        /* Allocate 20% more keypoints buffer than required */
        g_max_keypoints = max_output_keypoints * 1.2;
        return std::make_shared<OrbDescriptor>(gpuObj);
    }

    OrbDescriptor(CmBase::Ptr gpuObj) : KernelBase(kOrbDescriptor, gpuObj)
    {
        keypoints_input_count_ = 0;

        DeviceBase *dev = gpuObj->GetDeviceBase();

        gaussian_buffer_.setDeviceBase(dev);
        keypoint_input_buffer_.setDeviceBase(dev);

        cmdlist_ = g_descriptor_command_list;
        max_keypoints_ = g_max_keypoints;
        LoadKernel("orb_descriptor_genx.bin", "orb_descriptor_GENX");
    }

    void CreateKernel(Vec8u &image_buffer, Vec32f &pattern_buffer, Vec32i &umax_buffer,
            Vec8u &descriptor_buffer);

    void UpdateOutputMat(std::vector<KeyType> &dst_keypoint, MatType &dst_descriptor,
        Vec8u &descriptor_buffer, uint32_t descriptor_offset, const uint32_t level,
        const uint32_t scaled_patch_size);

    void ConvertGaussianImage(Image8u &gaussian_image);
    void AddInputKeypoints(std::vector<PartKey> &src_keypoint);

    void Submit(Vec8u &descriptor_buffer);

private:

    CommandListIndex    cmdlist_;
    Vec8u            gaussian_buffer_;
    Vec32f           keypoint_input_buffer_;
    uint32_t            keypoints_input_count_;
    uint32_t            max_keypoints_;
    EventAction::Ptr    action_;
};

} //namespace gpu

#endif //!__ORB_DESCRIPTOR_H__


