// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "fast.h"
#include "orb.h"

namespace gpu
{

template<typename pt>
struct cmp_pt
{
    bool operator()(const pt&a, const pt&b) const
    {
       return a.pt.y < b.pt.y || (a.pt.y == b.pt.y && a.pt.x < b.pt.x);
    }
};

/* Callback function - fastnmskernel */
void ConvertToCVPartKey(unsigned int *gpu_buffer, std::vector<PartKey> &keypoints, bool nmsOn, size_t max_nms)
{
    auto count = gpu_buffer[0];

    if( count > max_nms )
    {
        std::cout << "\n Estimated keypoints size are less with actual keypoint size"
                  << "\n Please use orb_extractor::set_max_keypoints_gpu_buffer_size(<fast_buffer_size>,<fast_nms_buffer_size>);" << std::endl;
    }

    KeypointGPUBuffer  *pk = NULL;
    PtGPUBuffer  *pkP = NULL;

    keypoints.clear();

    keypoints.reserve(count);

    if(nmsOn)
    {
        pk = (KeypointGPUBuffer *)(gpu_buffer + 1);
    }
    else
    {
        pkP = (PtGPUBuffer *)(gpu_buffer + 1);
    }
    for (unsigned int i = 0; i < count; i++)
    {
        if(nmsOn)
            keypoints.push_back({{pk[i].x, pk[i].y}, (float)pk[i].response, 0.f});
        else
            keypoints.push_back({{pkP[i].pt.x, pkP[i].pt.y}, 0, 0.f});
    }
}

/* Callback function - fastKernel */
void UpdateGroupCount(unsigned int *gpu_buffer, void * group_dimension, ze_event_handle_t event, size_t max_fast)
{
    auto count = gpu_buffer[0];

    if( count > max_fast )
    {
        std::cout << "\n Estimated keypoints size are less with actual keypoint size"
                  << "\n please use orb_extractor::set_max_keypoints_gpu_buffer_size(<fast_buffer_size>,<fast_nms_buffer_size>);" << std::endl;
    }

    ze_group_count_t *dim = static_cast<ze_group_count_t *>(group_dimension);

    constexpr int width_block = 128;

    dim->groupCountX = (count + width_block- 1)/width_block;
    dim->groupCountY = 1; dim->groupCountZ = 1;

    // Host signal the event to run NMS
    LzSignalEvent(event);
}

void Fast::NmsKernel(Vec8u &src_buffer, const float edge_clip)
{
    const auto src_width = src_buffer.width();
    const auto src_height = src_buffer.height();
    auto src_surface = src_buffer.raw();
    auto keypoints_input_surface = keypoint_input_buffer_.raw();
    auto keypoints_output_surface = keypoint_output_buffer_.raw();

    ze_group_count_t *dim = static_cast<ze_group_count_t *>(nms_group_dimension_.raw());
    dim->groupCountX=1;
    dim->groupCountY=1;
    dim->groupCountZ=1;

    nms_kernel_->SetKernelType(kIndirectKernel);

    nms_kernel_->AddInputSurface(keypoints_input_surface);
    nms_kernel_->AddOutputSurface(keypoints_output_surface);

    nms_kernel_->SetCommandListIndex(cmdlist_);
    nms_kernel_->SetGroupCount(dim);

    nms_kernel_->AddWaitEvent(nms_wait_event_);
    nms_kernel_->SetArgs<decltype(src_surface)>(&src_surface);
    nms_kernel_->SetArgs<decltype(keypoints_input_surface)>(&keypoints_input_surface);
    nms_kernel_->SetArgs<decltype(keypoints_output_surface)>(&keypoints_output_surface);
    nms_kernel_->SetArgs<decltype(src_width)>(&src_width);
    nms_kernel_->SetArgs<decltype(src_height)>(&src_height);
    nms_kernel_->SetArgs<decltype(src_width)>(&src_width);
    nms_kernel_->SetArgs<decltype(edge_clip)>(&edge_clip);

}

void Fast::MemsetKernel()
{
    auto keypoints_input_surface = keypoint_input_buffer_.raw();
    auto keypoints_output_surface = keypoint_output_buffer_.raw();

    memset_kernel_->SetCommandListIndex(cmdlist_);
    memset_kernel_->SetGroupCount(1, 1, 1);
    memset_kernel_->SetArgs<decltype(keypoints_input_surface)>(&keypoints_input_surface);
    memset_kernel_->SetArgs<decltype(keypoints_output_surface)>(&keypoints_output_surface);
}

void update_group_position(std::vector<int>& group_position_x, const uint32_t src_width,
    const uint32_t mono_width, const uint32_t cell_size, const uint32_t edge_clip,
    const uint32_t overlap)
{
  int blk_idx = 0;
  int pos = 0;
  int image_count = 0;
  int current_width = mono_width;

  while (1)
  {
    if (pos + cell_size < current_width - edge_clip)
    {
      pos = blk_idx++ * cell_size + mono_width * image_count + edge_clip;
      group_position_x.push_back(pos);

      if (pos > src_width - edge_clip)
      {
        group_position_x.pop_back();
        break;
      }
    }
    else
    {
        blk_idx = 0;
        image_count++;
        current_width += mono_width;
    }
  }

}

void Fast::CreateKernel(Image8u &src_image, Vec8u &src_buffer, Vec8u &mask_image,
        const double scale_factor, const bool mask_check, const uint32_t mask_step,
        const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
        const uint32_t overlap, const uint32_t cell_size, const uint32_t num_image,
        bool nmsOn)
{
    nms_on_ = nmsOn;
    constexpr int width_block = 16;  // Need to match with kernel
    constexpr int height_block = 16; // Need to match with kernel

    const auto src_width = src_image.width();
    const auto src_height = src_image.height();
    const auto mono_width = (int) (src_width / num_image);

    auto scale = (float) scale_factor;

    auto min_border_x = edge_clip;
    auto min_border_y = min_border_x;
    auto max_border_x = src_width - edge_clip;
    auto max_border_y = src_height - edge_clip;

    if ((min_border_x > max_border_x) || (min_border_y > max_border_y))
    {
        throw std::out_of_range("Unsupported scale factor\n");
    }

    auto width = max_border_x - min_border_x;
    auto height = max_border_y - min_border_y;

    auto w_cell = cell_size + overlap;
    auto h_cell = cell_size + overlap;

    auto thread_width_in_block = divUp(w_cell, width_block);
    auto thread_height_in_block = divUp(h_cell, height_block);

    auto width_in_block = divUp(width, cell_size);
    auto height_in_block = divUp(height, cell_size);

    std::vector<int> group_position_x;
    group_position_x.reserve(width_in_block);

    update_group_position(group_position_x, src_width, mono_width, cell_size, edge_clip, overlap);

    group_start_position_.resize(group_position_x.size());
    group_start_position_.upload(group_position_x.data(), kImmediate);

    width_in_block = group_position_x.size();

    if (((ini_threshold > 20) && (ini_threshold < 1)) ||
            ((min_threshold > 20) && (ini_threshold < 1)))
    {
        throw std::out_of_range("Threshold should range from 1 to 20");
    }

    auto src_surface = src_image.raw();
    auto keypoints_surface = keypoint_input_buffer_.raw();
    auto mask_surface = mask_image.raw();
    auto position_surface = group_start_position_.raw();

    SetCommandListIndex(cmdlist_);
    SetGroupSize(thread_width_in_block, thread_height_in_block, 1);
    SetGroupCount(width_in_block, height_in_block, 1);

    SetArgs<decltype(src_surface)>(&src_surface);
    SetArgs<decltype(keypoints_surface)>(&keypoints_surface);
    if (mask_check == 0)
        SetArgs<decltype(mask_surface)>(nullptr);
    else
        SetArgs<decltype(mask_surface)>(&mask_surface);
    SetArgs<decltype(position_surface)>(&position_surface);
    SetArgs<decltype(ini_threshold)>(&ini_threshold);
    SetArgs<decltype(min_threshold)>(&min_threshold);
    SetArgs<decltype(overlap)>(&overlap);
    SetArgs<decltype(cell_size)>(&cell_size);
    SetArgs<decltype(edge_clip)>(&edge_clip);
    SetArgs<decltype(max_border_x)>(&max_border_x);
    SetArgs<decltype(max_border_y)>(&max_border_y);
    SetArgs<decltype(scale)>(&scale);
    SetArgs<decltype(mask_check)>(&mask_check);
    SetArgs<decltype(mask_step)>(&mask_step);
    SetArgs<decltype(mono_width)>(&mono_width);

    if(nms_on_)
    {
        nms_wait_event_ = GetHostEvent();
        NmsKernel(src_buffer, edge_clip);
    }
    else
    {
        fast_post_event_ = gpuDev_->CreateEvent();
    }

    MemsetKernel();
}

void Fast::AddOutputKeypoint(std::vector<PartKey> &keypoints)
{
    if(nms_on_)
    {
        fast_post_event_ = gpuDev_->CreateEvent();
        AddEventToKernel(fast_post_event_);
        fast_action_.reset();
        fast_action_ = std::make_shared<EventAction>();
        auto keypoint_input_buffer = keypoint_input_buffer_.data();
        void  *pargs = nms_group_dimension_.raw();

        fast_action_->BindAction(fast_post_event_, &UpdateGroupCount, keypoint_input_buffer,pargs,
            nms_wait_event_, max_fast_);;

        AppendAction(fast_post_event_, fast_action_);

        nms_action_.reset();
        nms_action_ = std::make_shared<EventAction>();

        auto nms_output_buffer = keypoint_output_buffer_.data();

        nms_post_event_ = gpuDev_->CreateEvent();
        nms_kernel_->AddEventToKernel(nms_post_event_);
        nms_action_->BindAction(nms_post_event_, &ConvertToCVPartKey, nms_output_buffer, std::ref(keypoints), nms_on_, max_nms_);

        AppendAction(nms_post_event_, nms_action_, 1);
    }
    else
    {
        fast_post_event_ = gpuDev_->CreateEvent();
        AddEventToKernel(fast_post_event_);
        fast_action_.reset();
        fast_action_ = std::make_shared<EventAction>();
        auto keypoint_input_buffer = keypoint_input_buffer_.data();

        fast_action_->BindAction(fast_post_event_, &ConvertToCVPartKey, keypoint_input_buffer, std::ref(keypoints), nms_on_, max_nms_);;

        AppendAction(fast_post_event_, fast_action_);
    }
}

void Fast::Submit()
{
    // Memory leak in zeCommandListAppendMemoryFill.  Use a kernel to reset keypoint count
    memset_kernel_->SubmitKernel(memset_kernel_->GetKernelType());

    if (nms_post_event_ != nullptr) {
        AppendResetEvent(nms_wait_event_);
        AppendResetEvent(nms_post_event_);
    }

    SubmitKernel(GetKernelType());
    if(nms_on_)
    {
        // Download to CPU
        keypoint_input_buffer_.download(keypoint_input_buffer_.data(), cmdlist_,
                1, fast_post_event_);

        nms_kernel_->SubmitKernel(nms_kernel_->GetKernelType());

        keypoint_output_buffer_.download(keypoint_output_buffer_.data(), cmdlist_,
                keypoint_output_buffer_.size(), nms_post_event_);
    }
    else
    {
        keypoint_input_buffer_.download(keypoint_input_buffer_.data(), cmdlist_,
                keypoint_input_buffer_.size(), fast_post_event_);
    }
}


} // namespace gpu
