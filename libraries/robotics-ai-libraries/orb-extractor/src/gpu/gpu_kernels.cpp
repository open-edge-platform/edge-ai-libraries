// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include "gpu_kernels.h"

#include <any>
#include <map>
#include <tuple>

#include "orb.h"

namespace gpu
{
thread_local Device::Ptr ORBKernel::current_device = nullptr;

void ORBKernel::initializeGPU(
  uint32_t total_level, uint32_t num_images, uint32_t max_total_keypoints)
{
  // max_fast_keypoints  = max_total_keypoints;
  dev_keypoints.resize(total_level);
  dev_descriptors.resize(total_level);

  dev_fast_keypoints_tmp.resize(total_level);
  dev_fast_keypoints_count.resize(total_level);

  dev_fast_group_x.resize(total_level);
  dev_fast_group_y.resize(total_level);
}

void ORBKernel::setMaxkeypts(uint32_t max_total_keypoints)
{
  max_fast_keypoints = max_total_keypoints;
}

void ORBKernel::resize(
  const Image8u & src_image, Image8u & dst_image, const InterpolationType inter_type,
  const double fx, const double fy)
{
  resizeImpl(src_image, dst_image, inter_type, fx, fy, ORBKernel::current_device);
}

void ORBKernel::gaussianBlur(
  const Image8u & src_image, Image8u & dst_image, const short kernel_size, BorderTypes border)
{
  if (kernel_size != 7) {
    throw("Gaussian Blur only support kernel size of 7");
    return;
  }

  gaussianBlurImpl(
    src_image, dst_image, dev_gaussian_kernelX, dev_gaussian_kernelY, kernel_size, border,
    ORBKernel::current_device);
}

void ORBKernel::fastExt(
  const Image8u & src_image, const Image8u & mask_image, const bool mask_check,
  const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
  const uint32_t overlap, const uint32_t cell_size, const uint32_t num_image, const uint32_t level,
  bool nmsOn)
{
  if (dev_fast_keypoints_tmp.empty()) dev_fast_keypoints_tmp.resize(level + 1);

  if (dev_fast_keypoints_count.empty()) dev_fast_keypoints_count.resize(level + 1);

  if (dev_fast_group_x.empty()) dev_fast_group_x.resize(level + 1);

  if (dev_fast_group_y.empty()) dev_fast_group_y.resize(level + 1);

  fastExtImpl(
    src_image, mask_image, mask_check, ini_threshold, min_threshold, edge_clip, overlap, cell_size,
    num_image, nmsOn, max_fast_keypoints, dev_fast_group_x.at(level), dev_fast_group_y.at(level),
    dev_fast_keypoints_tmp.at(level), dev_fast_keypoints_count.at(level),
    ORBKernel::current_device);
}

void ORBKernel::downloadKeypoints(std::vector<PartKey> & keypoint_at_level, const uint32_t level)
{
  if (dev_fast_keypoints_tmp.empty() || dev_fast_keypoints_count.empty()) {
    throw std::logic_error("Need to run fastExt before downloadKeypoints");
  }

  dev_fast_keypoints_tmp.at(level).sync();
  dev_fast_keypoints_count.at(level).sync();

  int num_keypoints = dev_fast_keypoints_count.at(level).data()[0];

  keypoint_at_level.clear();

  keypoint_at_level.insert(
    keypoint_at_level.end(), dev_fast_keypoints_tmp.at(level).data(),
    dev_fast_keypoints_tmp.at(level).data() + num_keypoints);
}

void ORBKernel::orbDescriptor(
  const std::vector<PartKey> & src_keypoints, const Image8u & src_image,
  const Image8u & gaussian_image, const Vec32f & pattern_buffer, const Vec32i & umax_buffer,
  const uint32_t level)

{
  if (dev_keypoints.empty()) dev_keypoints.resize(level + 1);

  if (dev_descriptors.empty()) dev_descriptors.resize(level + 1);

  orbDescriptorImpl(
    src_keypoints, src_image, gaussian_image, pattern_buffer, umax_buffer, dev_keypoints.at(level),
    dev_descriptors.at(level), ORBKernel::current_device);
}

void ORBKernel::downloadKeypointsDescriptors(
  std::vector<KeyType> & keypoints_at_level, MatType & descriptor, const uint32_t descriptor_offset,
  const uint32_t level, const uint32_t scaled_patch_size, const float scale_factor, bool scale)
{
  if (dev_keypoints.empty() || dev_descriptors.empty()) {
    throw std::logic_error("Need to run orbDescriptor before downloadKeypointsDescriptors");
  }

  dev_keypoints.at(level).sync();
  dev_descriptors.at(level).sync();

  keypoints_at_level.clear();

  PartKey * pk = dev_keypoints.at(level).data();

  int num_keypoints = dev_keypoints.at(level).size();
  keypoints_at_level.reserve(num_keypoints);

  if (scale) {
    for (auto i = 0; i < num_keypoints; i++) {
      keypoints_at_level.emplace_back(
        pk[i].pt.x * scale_factor, pk[i].pt.y * scale_factor, scaled_patch_size, pk[i].angle,
        pk[i].response, level);
    }
  } else {
    for (auto i = 0; i < num_keypoints; i++) {
      keypoints_at_level.emplace_back(
        pk[i].pt.x, pk[i].pt.y, scaled_patch_size, pk[i].angle, pk[i].response, level);
    }
  }

#ifdef OPENCV_FREE
  memcpy(
    descriptor.data() + descriptor_offset, dev_descriptors.at(level).data(), num_keypoints * 32);
#else
  memcpy(descriptor.data + descriptor_offset, dev_descriptors.at(level).data(), num_keypoints * 32);
#endif
}

}  // namespace gpu
