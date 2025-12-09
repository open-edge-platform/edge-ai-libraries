// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#ifndef __GPU_KERNELS_H__
#define __GPU_KERNELS_H__

#include <map>

#include "device_array.h"
#include "device_impl.h"
#include "orb.h"
#include "orb_type.h"

#ifndef OPENCV_FREE
#include <opencv2/features2d.hpp>
#include <opencv2/opencv.hpp>
#endif

// extern int Device::myId;

namespace gpu
{

template <typename T, StorageOrder Order = ROW_MAJOR>
class DevImage : public DeviceMatrix<T, Order>
{
public:
  DevImage();
  DevImage(uint32_t rows, uint32_t cols);
  void resize(uint32_t rows, uint32_t cols);
};

template <typename T>
class DevArray : public DeviceArray<T>
{
public:
  DevArray();
  DevArray(std::size_t size);
  void resize(std::size_t size);
  void create(std::size_t size);
};

using Vec8u = DevArray<uint8_t>;
using Vec32f = DevArray<float>;
using Vec32i = DevArray<int>;
using Vec32u = DevArray<unsigned int>;
using Image8u = DevImage<uint8_t>;

class ORBKernel
{
public:
  using Ptr = std::shared_ptr<ORBKernel>;

  ORBKernel()
  {
    if (current_device.get() == nullptr)
    // if (!current_device)
    {
      current_device = std::make_unique<Device>();
      // std::cout << "sycl q=" << current_device->GetDeviceImpl()->get_queue()
      // << "\n";
    }

    max_fast_keypoints = 300000;
  }

  ~ORBKernel() {}

  static Device::Ptr get_current_device()
  {
    if (current_device.get() == nullptr) current_device = std::make_unique<Device>();
    return current_device;
  }

  void initializeGPU(uint32_t level, uint32_t num_images, uint32_t max_total_keypoints);

  void resize(
    const Image8u & src_image, Image8u & dst_image,
    const InterpolationType inter_type = kInterpolationLinear, const double fx = 0.0,
    const double fy = 0.0);

  void gaussianBlur(
    const Image8u & src_image, Image8u & dst_image, const short kernel_size, BorderTypes border);

  void fastExt(
    const Image8u & src_image, const Image8u & mask_image, const bool mask_check,
    const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
    const uint32_t overlap, const uint32_t cell_size, const uint32_t num_images,
    const uint32_t level, bool nmsOn = true);

  void downloadKeypoints(std::vector<PartKey> & keypoint_at_level, const uint32_t level);

  void orbDescriptor(
    const std::vector<PartKey> & src_keypoint, const Image8u & src_image,
    const Image8u & gaussian_image, const Vec32f & pattern_buffer, const Vec32i & umax_buffer,
    const uint32_t level);

  void downloadKeypointsDescriptors(
    std::vector<KeyType> & keypoint_at_level, MatType & descriptor,
    const uint32_t descriptor_offset, const uint32_t level, const uint32_t scaled_patch_size,
    const float scale_factor, bool scale = true);
  void setMaxkeypts(uint32_t max_total_keypoints);

private:
  template <typename T>
  void resizeImpl(
    const DevImage<T> & src_image, DevImage<T> & dst_image, const InterpolationType inter_type,
    const double fx, const double fy, Device::Ptr dev);

  template <typename T>
  void gaussianBlurImpl(
    const DevImage<T> & src_image, DevImage<T> & dst_image, DevImage<T> & kernelX,
    DevImage<T> & kernelY, const short kernel_size, BorderTypes border, Device::Ptr dev);

  template <typename T>
  void orbDescriptorImpl(
    const std::vector<PartKey> & src_keypoints, const DevImage<T> & src_image,
    const DevImage<T> & gaussian_image, const Vec32f & pattern, const Vec32i & umax,
    DevArray<PartKey> & dst_keypoint, Vec8u & dst_descriptor, Device::Ptr);

  template <typename T>
  void fastExtImpl(
    const DevImage<T> & src_image, const DevImage<T> & mask_image, const bool mask_check,
    const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
    const uint32_t overlap, const uint32_t cell_size, const uint32_t num_images, const bool nmsOn,
    const uint32_t max_keypoints_size, DevArray<sycl::int2> & group_x,
    DevArray<sycl::int2> & group_y, DevArray<PartKey> & dev_keypoints_tmp,
    Vec32u & dev_keypoints_count, Device::Ptr dev);

  std::vector<DevArray<PartKey>> dev_keypoints;
  std::vector<Vec8u> dev_descriptors;
  std::vector<DevArray<PartKey>> dev_fast_keypoints_tmp;
  std::vector<Vec32u> dev_fast_keypoints_count;
  DevImage<uint8_t> dev_gaussian_kernelX;
  DevImage<uint8_t> dev_gaussian_kernelY;
  std::vector<DevArray<sycl::int2>> dev_fast_group_x;
  std::vector<DevArray<sycl::int2>> dev_fast_group_y;
  uint32_t max_fast_keypoints;
  static thread_local Device::Ptr current_device;
};

// DevImage implementation
template <typename T, StorageOrder Order>
DevImage<T, Order>::DevImage() : DeviceMatrix<T, Order>(ORBKernel::get_current_device())
{
}

template <typename T, StorageOrder Order>
DevImage<T, Order>::DevImage(uint32_t rows, uint32_t cols)
: DeviceMatrix<T, Order>(rows, cols, ORBKernel::get_current_device())
{
}

template <typename T, StorageOrder Order>
void DevImage<T, Order>::resize(uint32_t rows, uint32_t cols)
{
  DeviceMatrix<T, Order>::resize(rows, cols, ORBKernel::get_current_device());
}

template <typename T>
DevArray<T>::DevArray() : DeviceArray<T>(ORBKernel::get_current_device())
{
}

template <typename T>
DevArray<T>::DevArray(size_t size) : DeviceArray<T>(size, ORBKernel::get_current_device())
{
}

template <typename T>
void DevArray<T>::resize(size_t size)
{
  DeviceArray<T>::resize(size, ORBKernel::get_current_device());
}

template <typename T>
void DevArray<T>::create(size_t size)
{
  DeviceArray<T>::create(size, ORBKernel::get_current_device());
}

}  // namespace gpu

#endif  // !__GPU_KERNELS_H__
