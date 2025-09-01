// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __FAST_H__
#define __FAST_H__

#include "kernel_base.h"
#include "gpu_kernels.h"

namespace gpu
{

static CommandListIndex g_fast_command_list;

class Fast : public KernelBase
{
public:

    using Ptr = std::shared_ptr<Fast>;

    static Ptr New(CommandListIndex index, const size_t max_nms_keypts,
        const size_t max_fast_keypts, const uint32_t num_image, CmBase::Ptr gpuObj)
    {
        g_fast_command_list = index;
        return std::make_shared<Fast>(max_nms_keypts, max_fast_keypts, num_image, gpuObj);
    }

    Fast(const size_t max_nms_keypts, const size_t max_fast_keypts, const uint32_t num_image, CmBase::Ptr gpuObj)
      : KernelBase(kFast, gpuObj), nms_wait_event_(nullptr),
         fast_post_event_(nullptr), nms_post_event_(nullptr), nms_on_(true)
    {
        size_t max_fast_keypoints = max_fast_keypts;
        max_fast_ = max_fast_keypoints;
        size_t keypoint_fast_buffer_size = max_fast_keypoints;
        size_t max_nms_keypoints = max_nms_keypts;
        max_nms_ = max_nms_keypoints;
        const size_t keypoint_nms_buffer_size =  max_nms_keypoints;

        DeviceBase *dev = gpuObj->GetDeviceBase();

        keypoint_input_buffer_.setDeviceBase(dev);
        keypoint_output_buffer_.setDeviceBase(dev);
        keypoint_count_buffer_.setDeviceBase(dev);
        group_start_position_.setDeviceBase(dev);
        nms_group_dimension_.setDeviceBase(dev);

        keypoint_input_buffer_.resize(keypoint_fast_buffer_size);
        keypoint_output_buffer_.resize(keypoint_nms_buffer_size);
        keypoint_count_buffer_.resize(1);
        nms_group_dimension_.resize(sizeof(ze_group_count_t));

        cmdlist_ = g_fast_command_list;

        LoadKernel("fastext_genx.bin", "fastext_GENX");

        nms_kernel_ = KernelBase::New(kFastNMS, gpuObj);
        nms_kernel_->LoadKernel("fastnmsext_genx.bin", "fastnmsext_GENX");

        // Workaround kernel.  Remove once zeCommandListAppendMemoryFill memory leak resolve
        memset_kernel_ = KernelBase::New(kMemset, gpuObj);
        memset_kernel_->LoadKernel("fastclear_genx.bin", "fastclear_GENX");
    }

    ~Fast() {}

    void CreateKernel(Image8u &src_image, Vec8u &src_buffer, Vec8u &mask_image,
            const double scale_factor, const bool mask_check, const uint32_t mask_step,
            const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
            const uint32_t overlap, const uint32_t cell_size, const uint32_t num_image, bool nmsOn = true);

    void AddOutputKeypoint(std::vector<PartKey> &keypoints);

    void Submit();

private:

    void NmsKernel(Vec8u &src_buffer, const float edge_clip);
    void MemsetKernel();

    bool                nms_on_;
    KernelBase::Ptr     nms_kernel_;
    KernelBase::Ptr     memset_kernel_;
    CommandListIndex    cmdlist_;
    Vec32u              keypoint_input_buffer_;
    Vec32u              keypoint_output_buffer_;
    Vec32u              keypoint_count_buffer_;
    Vec32u              group_start_position_;
    Vec8u               nms_group_dimension_;
    ze_event_handle_t   nms_wait_event_;
    ze_event_handle_t   fast_post_event_;
    ze_event_handle_t   nms_post_event_;
    EventAction::Ptr    fast_action_;
    EventAction::Ptr    nms_action_;
    size_t              max_fast_;
    size_t              max_nms_;
};

} //namespace gpu

#endif // __FAST_H__
