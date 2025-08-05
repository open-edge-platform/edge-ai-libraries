// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "gpu_kernels.h"
#include "kernel_base.h"
#include <tuple>
#include <any>
#include <map>

#include "orb.h"
#include "fast.h"
#include "resize.h"
#include "gaussian.h"
#include "orb_descriptor.h"

namespace gpu
{
using ResizeParamType = std::tuple<void *, void *, double, double>;
using GaussianParamType = std::tuple<void *, void *, short, double>;
using FastParamType = std::tuple<void *, double>;
using DescriptorParamType = std::tuple<void *, void *>;

KernelParamQueuePtr ORBKernel::getKernelQueue(OrbKernelType type)
{
    KernelParamQueuePtr kernel_queue;

    if (g_orb_kernel_list.find(type) == g_orb_kernel_list.end())
    {
        kernel_queue = std::make_shared<KernelParamQueue>();
    }
    else
    {
        kernel_queue = g_orb_kernel_list[type];
    }

    return kernel_queue;
}

template<typename T>
KernelBase::Ptr ORBKernel::getKernelFromQueue(KernelParamQueuePtr queue, T &arg)
{
    KernelBase::Ptr kernel = nullptr;

    for (const auto &it : *queue)
    {
        auto it_ = std::static_pointer_cast<OrbKernelParam<T>>(it);

        auto params = it_->getParams();

        if (params == arg)
        {
            kernel = it_->getKernel();
        }
    }

    return kernel;
}

template<typename T>
bool ORBKernel::requireNewKernel(KernelParamQueuePtr queue, T &arg)
{
    bool new_kernel = true;

    for (const auto &it : *queue)
    {
        auto it_ = std::static_pointer_cast<OrbKernelParam<T>>(it);

        auto aparams = it_->getParams();

        if (aparams == arg)
        {
            new_kernel = false;
        }
    }

    return new_kernel;
}

template<typename T>
void ORBKernel::addToKernelQueue(KernelBase::Ptr kernel, OrbKernelType type, T &arg,
        KernelParamQueuePtr queue)
{
    auto kernelParam = OrbKernelParam<T>::New();
    kernelParam->setParams(std::move(arg));
    kernelParam->setKernel(std::move(kernel));

    (*queue).push_back(std::move(kernelParam));
    g_orb_kernel_list[type] = std::move(queue);
}

DeviceBase * ORBKernel::getDeviceBase()
{
    return deviceBase_;
}

void ORBKernel::initializeGPU(uint32_t max_total_keypoints)
{
    uint32_t descriptor_size = max_total_keypoints * 2 * 32;
    descriptor_size = ((uint32_t)(descriptor_size / 32)) * 32;
    g_descriptor_buffer.resize(descriptor_size);
}

void ORBKernel::setKernelPath(std::string path)
{
    gpuDev_->SetKernelPath(std::move(path));
}

void ORBKernel::resize(Vec8u &src_image, Vec8u &dst_image, const InterpolationType inter_type,
        const double fx, const double fy)
{
    /* Submit to cmd list kAppend/kCmdList0 */
    CommandListIndex cmdlist_index = kAppend;

    const auto src_width = src_image.width();
    const auto src_height = src_image.height();
    auto dst_width = dst_image.width();
    auto dst_height = dst_image.height();

    if ((dst_width == 0) || (dst_height == 0))
    {
        dst_width = fx * src_width;
        dst_height = fy * src_height;

        dst_image.resize(dst_width, dst_height);
    }

    /* check if cmd list constructed, or need to update(reset the list) */
    ResizeParamType arglist = std::make_tuple(src_image.raw(), dst_image.raw(), fx, fy);

    KernelParamQueuePtr kernel_queue = getKernelQueue(kResize);

    bool create_new_kernel = requireNewKernel<ResizeParamType>(kernel_queue, arglist);

    if (create_new_kernel)
    {
        Resize::Ptr resize_kernel = Resize::New(cmdlist_index, gpuDev_);
        resize_kernel->CreateKernel(src_image, dst_image, fx, fy, inter_type);

        addToKernelQueue<ResizeParamType>(resize_kernel, kResize, arglist,
                std::move(kernel_queue));

        resize_kernel->Submit();
    }
    else
    {
        auto resize_base = getKernelFromQueue<ResizeParamType>(std::move(kernel_queue), arglist);
        auto resize_kernel = std::reinterpret_pointer_cast<Resize>(resize_base);

        resize_kernel->Submit();
    }

}

void ORBKernel::gaussianBlur(Image8u &src_image, Image8u &dst_image, const short kernel_size, const double sigma)
{
    /* Submit to cmd list kAppend/kCmdList0 */
    CommandListIndex cmdlist_index = kAppend;

    GaussianParamType arglist = std::make_tuple(src_image.raw(), dst_image.raw(), kernel_size, sigma);

    KernelParamQueuePtr kernel_queue = getKernelQueue(kGaussian);

    bool create_new_kernel = requireNewKernel<GaussianParamType>(kernel_queue, arglist);

    if (create_new_kernel)
    {
        GaussianBlur::Ptr gaussian_kernel = GaussianBlur::New(cmdlist_index, gpuDev_);
        gaussian_kernel->CreateKernel(src_image, dst_image, sigma);

        addToKernelQueue<GaussianParamType>(gaussian_kernel, kGaussian, arglist, std::move(kernel_queue));

        gaussian_kernel->Submit();
    }
    else
    {
        auto gaussian_base = getKernelFromQueue<GaussianParamType>(std::move(kernel_queue), arglist);
        auto gaussian_kernel = std::reinterpret_pointer_cast<GaussianBlur>(gaussian_base);

        gaussian_kernel->Submit();
    }
}

void ORBKernel::fastExt(Image8u &src_image, Vec8u &src_buffer, std::vector<PartKey> &keypoints,
        Vec8u &mask_image, const double scale_factor, const bool mask_check, const uint32_t mask_step,
        const uint32_t ini_threshold, const uint32_t min_threshold, const uint32_t edge_clip,
        const uint32_t overlap, const uint32_t cell_size, const uint32_t num_image,
        const size_t max_nms_keypts, const size_t max_fast_keypts, bool nmsOn)

{
    /* Submit to cmd list kAppend/kCmdList0 */
    CommandListIndex cmdlist_index = kAppend;
    /* check if cmd list constructed, or need to update(reset the list) */

    FastParamType arglist = std::make_tuple(src_buffer.raw(), scale_factor);

    KernelParamQueuePtr kernel_queue = getKernelQueue(kFast);

    bool create_new_fast_kernel = requireNewKernel<FastParamType>(kernel_queue, arglist);

    if (create_new_fast_kernel)
    {
        Fast::Ptr fast_kernel = Fast::New(cmdlist_index, max_nms_keypts, max_fast_keypts, num_image, gpuDev_);
        fast_kernel->CreateKernel(src_image, src_buffer, mask_image, scale_factor, mask_check,
                mask_step, ini_threshold, min_threshold, edge_clip, overlap, cell_size, num_image, nmsOn);

        fast_kernel->AddOutputKeypoint(keypoints);

        addToKernelQueue<FastParamType>(fast_kernel, kFast, arglist, std::move(kernel_queue));

        fast_kernel->Submit();
    }
    else
    {
        auto kernel_base = getKernelFromQueue<FastParamType>(std::move(kernel_queue), arglist);
        auto fast_kernel = std::reinterpret_pointer_cast<Fast>(kernel_base);
        fast_kernel->AddOutputKeypoint(keypoints);

        fast_kernel->Submit();
    }
}

void ORBKernel::orbDescriptor(std::vector<PartKey> &src_keypoint, Vec8u &image_buffer, Image8u &gaussian_image,
        Vec32f &pattern_buffer, Vec32i &umax_buffer, std::vector<KeyType> &dst_keypoint,
        const uint32_t level, const uint32_t scaled_patch_size, MatType &dst_descriptor,
        uint32_t descriptor_offset, uint32_t max_keypoint_per_level)

{
    /* Submit to cmd list kCmdList1 */
    CommandListIndex cmdlist_index = kCmdList1;

    DescriptorParamType arglist = std::make_tuple(image_buffer.raw(), gaussian_image.raw());

    KernelParamQueuePtr kernel_queue = getKernelQueue(kOrbDescriptor);

    bool create_new_descriptor_kernel = requireNewKernel<DescriptorParamType>(kernel_queue, arglist);

    if (create_new_descriptor_kernel)
    {
        OrbDescriptor::Ptr descriptor_kernel = OrbDescriptor::New(cmdlist_index,
                max_keypoint_per_level, gpuDev_);

        descriptor_kernel->AddInputKeypoints(src_keypoint);

        descriptor_kernel->ConvertGaussianImage(gaussian_image);
        descriptor_kernel->CreateKernel(image_buffer, pattern_buffer, umax_buffer,
                g_descriptor_buffer);

        descriptor_kernel->UpdateOutputMat(dst_keypoint, dst_descriptor, g_descriptor_buffer,
                descriptor_offset, level, scaled_patch_size);

        descriptor_kernel->Submit(g_descriptor_buffer);

        addToKernelQueue<DescriptorParamType>(descriptor_kernel, kOrbDescriptor, arglist, std::move(kernel_queue));
    }
    else
    {
        auto kernel_base = getKernelFromQueue<DescriptorParamType>(std::move(kernel_queue), arglist);
        auto descriptor_kernel = std::reinterpret_pointer_cast<OrbDescriptor>(kernel_base);

        descriptor_kernel->AddInputKeypoints(src_keypoint);
        descriptor_kernel->ConvertGaussianImage(gaussian_image);

        descriptor_kernel->UpdateOutputMat(dst_keypoint, dst_descriptor, g_descriptor_buffer,
                descriptor_offset, level, scaled_patch_size);

        descriptor_kernel->Submit(g_descriptor_buffer);

    }

}

void ORBKernel::execute(CommandListIndex cmd_idx)
{
    gpuDev_->ExecuteGraph(cmd_idx);
}

} // namespace gpu
