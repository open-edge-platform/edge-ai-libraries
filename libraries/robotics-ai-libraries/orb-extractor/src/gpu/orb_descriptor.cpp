// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "orb_descriptor.h"
#include "orb.h"

namespace gpu
{
/* Callback function - orbDescriptorKernel*/
void ConvertToCVKeypointAndDescriptor(float *gpu_keypoint_buffer, uint32_t keypoint_count,
        std::vector<KeyType> &keypoints, unsigned char *gpu_descriptor_buffer, MatType &descriptor,
        uint32_t descriptor_offset, uint32_t level, uint32_t scaled_patch_size)
{
    KeypointGPUBufferFloat  *pk = (KeypointGPUBufferFloat *)gpu_keypoint_buffer;

    keypoints.clear();
    keypoints.reserve(keypoint_count);
    for (unsigned int i = 0; i < keypoint_count; i++)
    {
        keypoints.emplace_back(pk[i].x, pk[i].y, scaled_patch_size, pk[i].angle,
                pk[i].response, level);
    }

#ifdef OPENCV_FREE
    memcpy(descriptor.data() + descriptor_offset, gpu_descriptor_buffer + descriptor_offset, keypoint_count*32);
#else
    memcpy(descriptor.data + descriptor_offset, gpu_descriptor_buffer + descriptor_offset, keypoint_count*32);
#endif
}

void OrbDescriptor::CreateKernel (Vec8u &image_buffer, Vec32f &pattern_buffer,
        Vec32i &umax_buffer, Vec8u &descriptor_buffer)
{
    constexpr uint32_t width_block = 16;
    constexpr uint32_t block_per_thread = 2;

    constexpr uint32_t block_size = width_block * block_per_thread;
    const uint32_t gridx = divUp(keypoints_input_count_, block_size);

    SetCommandListIndex(cmdlist_);

    SetGroupCount(gridx, 1, 1);

    auto image_width = image_buffer.width();

    auto keypoint = keypoint_input_buffer_.raw();
    auto image = image_buffer.raw();
    auto gaussian = gaussian_buffer_.raw();
    auto pattern = pattern_buffer.raw();
    auto descriptor = descriptor_buffer.raw();
    auto umax = umax_buffer.raw();

    uint32_t descriptor_offset = 0;

    SetArgs<decltype(keypoint)>(&keypoint);
    SetArgs<decltype(image)>(&image);
    SetArgs<decltype(gaussian)>(&gaussian);
    SetArgs<decltype(pattern)>(&pattern);
    SetArgs<decltype(descriptor)>(&descriptor);
    SetArgs<decltype(umax)>(&umax);
    SetArgs<decltype(keypoints_input_count_)>(&keypoints_input_count_);
    SetArgs<decltype(image_width)>(&image_width);
    SetArgs<decltype(descriptor_offset)>(&descriptor_offset);
}

void OrbDescriptor::AddInputKeypoints(std::vector<PartKey> &src_keypoint)
{
    if (keypoint_input_buffer_.size() == 0)
    {
        uint32_t keypoint_buffer_size = max_keypoints_ * 2.0 * sizeof(KeypointGPUBufferFloat);

        keypoint_input_buffer_.resize(keypoint_buffer_size);
    }

    keypoints_input_count_ = src_keypoint.size();

    auto pt = (KeypointGPUBufferFloat *)keypoint_input_buffer_.raw();

    int i = 0;
    for (auto &kpt : src_keypoint)
    {
        pt[i].x = kpt.pt.x;
        pt[i].y = kpt.pt.y;
        pt[i].response = kpt.response;
        pt[i].angle = 0.f;
        i++;
    }
}

void OrbDescriptor::ConvertGaussianImage(Image8u &gaussian_image)
{
    if ((gaussian_buffer_.width() == 0) && (gaussian_buffer_.height() == 0))
    {
        gaussian_buffer_.resize(gaussian_image.width(), gaussian_image.height(), kDeviceMemory);
    }

    gaussian_buffer_.upload(gaussian_image.raw(), cmdlist_);
}

void OrbDescriptor::UpdateOutputMat(std::vector<KeyType> &dst_keypoint,
        MatType &dst_descriptor, Vec8u &descriptor_buffer, uint32_t descriptor_offset,
        const uint32_t level, const uint32_t scaled_patch_size)
{
    ze_event_handle_t event = gpuDev_->CreateEvent();
    AddEventToKernel(event);

    // Need to modify the kernel with new descriptor offset
    SetArgs<decltype(descriptor_offset)>(&descriptor_offset, 8);

    action_.reset();
    action_ = std::make_shared<EventAction>();
    action_->BindAction(event, &ConvertToCVKeypointAndDescriptor, keypoint_input_buffer_.data(),
           keypoints_input_count_, std::ref(dst_keypoint), descriptor_buffer.data(),
           std::ref(dst_descriptor), descriptor_offset, level, scaled_patch_size);

    AppendAction(event, action_);
}

void OrbDescriptor::Submit(Vec8u &descriptor_buffer)
{
    SubmitKernel(GetKernelType());
}

} //namespace gpu
