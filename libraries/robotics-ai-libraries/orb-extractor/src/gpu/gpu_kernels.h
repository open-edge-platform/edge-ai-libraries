// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __GPU_KERNELS_H__
#define __GPU_KERNELS_H__

#include <map>

#include "orb_type.h"
#include "kernel_base.h"
#include "device_buffer.h"
#include "device_image.h"

#ifndef OPENCV_FREE
#include <opencv2/opencv.hpp>
#include <opencv2/features2d.hpp>
#endif

namespace gpu
{

class IOrbKernelParam {};

template<typename T>
class OrbKernelParam : public IOrbKernelParam
{
public:

    using Ptr = std::shared_ptr<OrbKernelParam>;

    static Ptr New()
    {
        return std::make_shared<OrbKernelParam>();
    }

    ~OrbKernelParam() { }

    void setParams(T _in) { inputParam = std::move(_in); }
    void setKernel(KernelBase::Ptr _kernel) { kernel = std::move(_kernel); }

    T                   getParams() { return inputParam; }
    KernelBase::Ptr     getKernel() { return kernel; }

private:
    KernelBase::Ptr kernel;
    T inputParam;
};


using KernelParamQueue = std::vector<std::shared_ptr<IOrbKernelParam>>;
using KernelParamQueuePtr = std::shared_ptr<KernelParamQueue>;

using ResizeParamType = std::tuple<void *, void *, double, double>;
using GaussianParamType = std::tuple<void *, void *, short, double>;
using FastParamType = std::tuple<void *, double>;
using DescriptorParamType = std::tuple<void *, void *>;


typedef struct _point {
    int x;
    int y;
} Point;

typedef struct _partKey {
    Point pt;
    float response;
    float angle;
} PartKey;

class ORBKernel
{
public:

  using Ptr = std::shared_ptr<ORBKernel>;

  ORBKernel()
  {
    gpuDev_ = std::make_unique<CmBase>();
    deviceBase_ = gpuDev_->GetDeviceBase();
    gpuDev_->CreateGraph(3);
    g_descriptor_buffer.setDeviceBase(deviceBase_);
  }

  ~ORBKernel() {};

  void initializeGPU(uint32_t max_keypoints_count);
  void setKernelPath(std::string path);
  void execute(CommandListIndex cmd_list_idx);

  DeviceBase *getDeviceBase();


  void resize(Vec8u &src_image, Vec8u &dst_image,
        const InterpolationType inter_type = kInterpolationLinear,
        const double fx = 0.0, const double fy = 0.0);

  void gaussianBlur(Image8u &src_image, Image8u &dst_image,
        const short kernel_size, const double sigma);

  void fastExt(Image8u &src_image, Vec8u &src_buffer, std::vector<PartKey> &keypoint,
        Vec8u &mask_image, const double scale_factor, const bool mask_check, const uint32_t mask_step,
        const uint32_t ini_threshold, const uint32_t min_threshold,
        const uint32_t edge_clip, const uint32_t overlap, const uint32_t cell_size,const uint32_t num_image,
        const size_t max_nms_keypts, const size_t max_fast_keypts, bool nmsOn = true);

  void orbDescriptor(std::vector<PartKey> &src_keypoint, Vec8u &image_buffer, Image8u &gaussian_image,
        Vec32f &pattern_buffer, Vec32i &umax_buffer, std::vector<KeyType> &dst_keypoint,
        const uint32_t level, const uint32_t scaled_patch_size, MatType &dst_descriptor,
        const uint32_t descriptor_offset, const uint32_t max_keypoint_per_level);
private:

  KernelParamQueuePtr getKernelQueue(OrbKernelType type);

  template<typename T>
  KernelBase::Ptr getKernelFromQueue(KernelParamQueuePtr queue, T &arg);

  template<typename T>
  bool requireNewKernel(KernelParamQueuePtr queue, T &arg);


  template<typename T>
  void addToKernelQueue(KernelBase::Ptr kernel, OrbKernelType type, T &arg,
        KernelParamQueuePtr queue);

  std::map<OrbKernelType, KernelParamQueuePtr> g_orb_kernel_list;
  Vec8u g_descriptor_buffer;
  CmBase::Ptr gpuDev_;
  DeviceBase *deviceBase_;
};

} //namespace gpu

#endif // !__GPU_KERNELS_H__
