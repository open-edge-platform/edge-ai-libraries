// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions
// and limitations under the License.

// vim:ts=2:sw=2:et:

#pragma once

#ifndef L0_RT_HELPERS_H
#define L0_RT_HELPERS_H

#include <cstdio>
#include <cstdlib>
#include <assert.h>
#include <chrono>
#include <initializer_list>
#include <limits>
#include <tuple>
#include <thread>

#include <level_zero/ze_api.h>

#include "cm_utils.h"

#define L0_SAFE_CALL(call)                                                     \
  {                                                                            \
    auto status = (call);                                                      \
    if (status != 0) {                                                         \
      fprintf(stderr, "%s:%d: L0 error %x\n", __FILE__, __LINE__,              \
              (int)status);                                                    \
      exit(1);                                                                 \
    }                                                                          \
  }

//Find a GPU device and create a compute context
inline auto LzFindDevice()
{
    L0_SAFE_CALL(zeInit(ZE_INIT_FLAG_GPU_ONLY));

    // Discover all the driver instances
    uint32_t driverCount = 0;
    L0_SAFE_CALL(zeDriverGet(&driverCount, nullptr));

    ze_driver_handle_t *allDrivers =
        (ze_driver_handle_t *)malloc(driverCount * sizeof(ze_driver_handle_t));

    if (allDrivers == nullptr) {
        throw std::bad_alloc();
    }

    L0_SAFE_CALL(zeDriverGet(&driverCount, allDrivers));

    ze_driver_handle_t hDriver = nullptr;
    ze_device_handle_t hDevice = nullptr;
    for (uint32_t i = 0; i < driverCount; ++i) {
        uint32_t deviceCount = 0;
        hDriver = allDrivers[i];
        L0_SAFE_CALL(zeDeviceGet(hDriver, &deviceCount, nullptr));
        ze_device_handle_t *allDevices =
            (ze_device_handle_t *)malloc(deviceCount * sizeof(ze_device_handle_t));

        if (allDevices == nullptr) {
            throw std::bad_alloc();
        }

        L0_SAFE_CALL(zeDeviceGet(hDriver, &deviceCount, allDevices));
        for (uint32_t d = 0; d < deviceCount; ++d) {
            ze_device_properties_t device_properties;
            L0_SAFE_CALL(zeDeviceGetProperties(allDevices[d], &device_properties));
            if (ZE_DEVICE_TYPE_GPU == device_properties.type) {
                hDevice = allDevices[d];
                break;
            }
        }
        free(allDevices);
        if (nullptr != hDevice) {
            break;
        }
    }
    free(allDrivers);
    assert(hDriver);
    assert(hDevice);

    ze_context_desc_t contextDesc = {ZE_STRUCTURE_TYPE_CONTEXT_DESC, nullptr, 0};
    ze_context_handle_t hContext = nullptr;
    L0_SAFE_CALL(zeContextCreate(hDriver, &contextDesc, &hContext));

    return std::make_tuple(hDriver, hDevice, hContext);
}

inline auto LzFindDriverAndDevice() {
  return LzFindDevice();
}

inline ze_device_properties_t LzGetDeviceProperties(ze_device_handle_t hDevice)
{
    ze_device_properties_t device_properties;

    L0_SAFE_CALL(zeDeviceGetProperties(hDevice, &device_properties));

    return device_properties;

}

inline ze_command_queue_handle_t LzCreateCommandQueue(ze_context_handle_t hContext, ze_device_handle_t hDevice)
{
    // Create a command queue
    ze_command_queue_desc_t commandQueueDesc = {
        ZE_STRUCTURE_TYPE_COMMAND_QUEUE_DESC, nullptr, 0, 0, 0,
        //ZE_COMMAND_QUEUE_MODE_DEFAULT, ZE_COMMAND_QUEUE_PRIORITY_NORMAL,
        ZE_COMMAND_QUEUE_MODE_SYNCHRONOUS, ZE_COMMAND_QUEUE_PRIORITY_NORMAL};
    ze_command_queue_handle_t hCommandQueue;
    L0_SAFE_CALL(zeCommandQueueCreate(hContext, hDevice, &commandQueueDesc, &hCommandQueue));
    return hCommandQueue;
}

inline ze_command_list_handle_t LzCreateCommandList(ze_context_handle_t hContext, ze_device_handle_t hDevice)
{
    // Create a command list
    ze_command_list_desc_t commandListDesc = {
        ZE_STRUCTURE_TYPE_COMMAND_LIST_DESC, 0, 0, 0};
    ze_command_list_handle_t hCommandList;
    L0_SAFE_CALL(zeCommandListCreate(hContext, hDevice, &commandListDesc, &hCommandList));
    return hCommandList;
}

inline auto LzCreateCommandQueueAndList(ze_context_handle_t hContext, ze_device_handle_t hDevice)
{
    return std::tuple<ze_command_queue_handle_t, ze_command_list_handle_t>{
        LzCreateCommandQueue(hContext, hDevice), LzCreateCommandList(hContext, hDevice)};
}

//create command list for low-latency command submission
inline ze_command_list_handle_t LzCreateImmCommandList(ze_context_handle_t hContext, ze_device_handle_t hDevice)
{
    ze_command_queue_desc_t desc = {
        ZE_STRUCTURE_TYPE_COMMAND_QUEUE_DESC, nullptr, 0, 0,
        0,
        ZE_COMMAND_QUEUE_MODE_DEFAULT,
        ZE_COMMAND_QUEUE_PRIORITY_NORMAL,
    };
    ze_command_list_handle_t hCommandList = nullptr;
    L0_SAFE_CALL(zeCommandListCreateImmediate(hContext, hDevice, &desc, &hCommandList));
    return hCommandList;
}

inline ze_image_handle_t LzCreateImage2D(ze_context_handle_t hContext, ze_device_handle_t hDevice,
    ze_image_format_t &fmt, unsigned int width, unsigned int height)
{
    ze_image_handle_t hImage;
    ze_image_desc_t desc = {
        ZE_STRUCTURE_TYPE_IMAGE_DESC, nullptr,
        //0u,
        ZE_IMAGE_FLAG_KERNEL_WRITE,
        ZE_IMAGE_TYPE_2D,
        fmt, width, height, 0, 0, 0};
    L0_SAFE_CALL(zeImageCreate(hContext, hDevice, &desc, &hImage));

    return hImage;
}

inline ze_image_handle_t LzCreateBuffer(ze_context_handle_t hContext, ze_device_handle_t hDevice,
    unsigned int size)
{
    ze_image_handle_t hImage;
    ze_image_desc_t desc = {
        ZE_STRUCTURE_TYPE_IMAGE_DESC, nullptr,
        ZE_IMAGE_FLAG_KERNEL_WRITE,
        ZE_IMAGE_TYPE_BUFFER,
        {ZE_IMAGE_FORMAT_LAYOUT_32}, size, 0, 0, 0, 0};
    L0_SAFE_CALL(zeImageCreate(hContext, hDevice, &desc, &hImage));

    return hImage;
}

inline ze_image_handle_t LzCreateImage2D(ze_context_handle_t hContext, ze_device_handle_t hDevice,
    ze_command_list_handle_t hCommandList, ze_image_format_t &fmt,
    unsigned int width, unsigned int height, const void *pData = nullptr)
{
    ze_image_handle_t hImage;
    ze_image_desc_t desc = {
        ZE_STRUCTURE_TYPE_IMAGE_DESC, nullptr,
        pData ? 0u : ZE_IMAGE_FLAG_KERNEL_WRITE,
        ZE_IMAGE_TYPE_2D,
        fmt, width, height, 0, 0, 0};
    L0_SAFE_CALL(zeImageCreate(hContext, hDevice, &desc, &hImage));
    if (pData)
        L0_SAFE_CALL(zeCommandListAppendImageCopyFromMemory(hCommandList, hImage,
                                                            pData, nullptr, nullptr, 0, nullptr));
    return hImage;
}

inline ze_image_handle_t LzCreateImage3D(ze_context_handle_t hContext, ze_device_handle_t hDevice,
    ze_command_list_handle_t hCommandList, ze_image_format_t &fmt,
    unsigned int width, unsigned int height, unsigned int depth, const void *pData = nullptr)
{
    ze_image_handle_t hImage;
    ze_image_desc_t desc = {
        ZE_STRUCTURE_TYPE_IMAGE_DESC, nullptr,
        pData ? 0u : ZE_IMAGE_FLAG_KERNEL_WRITE,
        ZE_IMAGE_TYPE_3D,
        fmt, width, height, depth, 0, 0};
    L0_SAFE_CALL(zeImageCreate(hContext, hDevice, &desc, &hImage));
    if (pData)
        L0_SAFE_CALL(zeCommandListAppendImageCopyFromMemory(hCommandList, hImage,
                                                            pData, nullptr, nullptr, 0, nullptr));
    return hImage;
}

inline void LzAppendImageCopyFromMemory(ze_command_list_handle_t hCommandList, ze_image_handle_t hDstImage,
        const void *src, ze_event_handle_t hSignalEvent = nullptr, ze_event_handle_t *pWaitEvent = nullptr)
{
    L0_SAFE_CALL(zeCommandListAppendImageCopyFromMemory(hCommandList, hDstImage, src, nullptr, hSignalEvent,
                0, pWaitEvent));
    L0_SAFE_CALL(zeCommandListAppendBarrier(hCommandList, nullptr, 0, nullptr));
}

inline void LzAppendImageCopyToMemory(ze_command_list_handle_t hCommandList, ze_image_handle_t hSrcImage,
        void *dst, ze_event_handle_t hSignalEvent = nullptr, ze_event_handle_t *pWaitEvent = nullptr)
{
    L0_SAFE_CALL(zeCommandListAppendImageCopyToMemory(hCommandList, dst, hSrcImage, nullptr, hSignalEvent,
                0, pWaitEvent));
}

inline void LzAppendImageCopy(ze_command_list_handle_t hCommandList, ze_image_handle_t hSrcImage,
        ze_image_handle_t hDstImage, ze_event_handle_t hSignalEvent = nullptr,
        ze_event_handle_t *pWaitEvent = nullptr)
{
    L0_SAFE_CALL(zeCommandListAppendImageCopy(hCommandList, hDstImage, hSrcImage,
               hSignalEvent, 0, pWaitEvent));
}

inline auto LzGetImageProperties(ze_image_handle_t hImage)
{
    ze_image_memory_properties_exp_t prop;

    L0_SAFE_CALL(zeImageGetMemoryPropertiesExp(hImage, &prop));

    return std::make_tuple(prop.size, prop.rowPitch, prop.slicePitch);
}

inline ze_sampler_handle_t LzCreateSampler(ze_context_handle_t hContext, ze_device_handle_t hDevice, const ze_sampler_desc_t* kdesc)
{
    ze_sampler_handle_t hSampler;
    L0_SAFE_CALL(zeSamplerCreate(hContext, hDevice, kdesc, &hSampler));
    return hSampler;
}

inline void LzDestroy(ze_context_handle_t hContext)
{
#ifndef CMRT_EMU
    L0_SAFE_CALL(zeContextDestroy(hContext));
#endif
}

inline void LzDestroy(ze_command_list_handle_t hCommandList)
{
#ifndef CMRT_EMU
    L0_SAFE_CALL(zeCommandListDestroy(hCommandList));
#endif
}

inline void LzDestroy(ze_command_queue_handle_t hCommandQueue)
{
#ifndef CMRT_EMU
    L0_SAFE_CALL(zeCommandQueueDestroy(hCommandQueue));
#endif
}

inline void LzDestroy(ze_module_handle_t hModule)
{
#ifndef CMRT_EMU
    L0_SAFE_CALL(zeModuleDestroy(hModule));
#endif
}
inline void LzDestroyImage(ze_image_handle_t img)
{
    L0_SAFE_CALL(zeImageDestroy(img));
}

inline void LzDestroy(ze_sampler_handle_t sampler)
{
    L0_SAFE_CALL(zeSamplerDestroy(sampler));
}

inline void LzDestroy(ze_event_pool_handle_t pool)
{
#ifndef CMRT_EMU
    L0_SAFE_CALL(zeEventPoolDestroy(pool));
#endif
}

inline void* LzAllocDeviceMemory(ze_context_handle_t hContext, ze_device_handle_t hDevice,
    size_t size, size_t alignment = 4096)
{
    ze_device_mem_alloc_desc_t device_desc = {
        ZE_STRUCTURE_TYPE_DEVICE_MEM_ALLOC_DESC, nullptr,
        0,
        0
    };
    void *ptr = nullptr;
    L0_SAFE_CALL(zeMemAllocDevice(hContext, &device_desc, size,
        alignment, hDevice, &ptr));
    return ptr;
}

inline void* LzAllocSharedMemory(ze_context_handle_t hContext, ze_device_handle_t hDevice,
    size_t size, size_t alignment = 4096)
{
    ze_device_mem_alloc_desc_t device_desc = {
      ZE_STRUCTURE_TYPE_DEVICE_MEM_ALLOC_DESC, nullptr, 0, 0
    };
    ze_host_mem_alloc_desc_t host_desc = {
      ZE_STRUCTURE_TYPE_HOST_MEM_ALLOC_DESC, nullptr, 0
    };
    void *ptr = nullptr;
    L0_SAFE_CALL(zeMemAllocShared(hContext, &device_desc, &host_desc, size,
        alignment, hDevice, &ptr));
    return ptr;
}

inline void* LzAllocHostMemory(ze_context_handle_t hContext, size_t size, size_t alignment = 4096)
{

    ze_host_mem_alloc_desc_t host_desc = {
      ZE_STRUCTURE_TYPE_HOST_MEM_ALLOC_DESC, nullptr, 0
    };

    void *ptr = nullptr;
    L0_SAFE_CALL(zeMemAllocHost(hContext, &host_desc, size, alignment, &ptr));
    return ptr;
}


inline void LzFreeMemory(ze_context_handle_t hContext, void *ptr)
{
    L0_SAFE_CALL(zeMemFree(hContext, ptr));
#ifdef TEST_DEBUG
    std::cout << __func__ << " is OK\n";
#endif
}

inline ze_module_handle_t LzCreateModule(ze_context_handle_t hContext, ze_device_handle_t hDevice, const uint8_t* krn, size_t krn_size)
{
    ze_module_desc_t moduleDesc = {
        ZE_STRUCTURE_TYPE_MODULE_DESC, nullptr, //
#if defined(CM_COMPILE_SPIRV) || defined(OCLOC_SPIRV)
        ZE_MODULE_FORMAT_IL_SPIRV, //
#else // !CM_COMPILE_SPIRV
        ZE_MODULE_FORMAT_NATIVE, //
#endif // CM_COMPILE_SPIRV
        krn_size,  //
        krn, //
        "-cmc",
        nullptr
    };

    ze_module_handle_t hModule;
    L0_SAFE_CALL(zeModuleCreate(hContext, hDevice, &moduleDesc, &hModule, nullptr));
    return hModule;
}


inline ze_module_handle_t LzCreateModule(ze_context_handle_t hContext, ze_device_handle_t hDevice, const char *fn)
{
    const auto krn = cm_utils::read_binary_file<uint8_t>(fn);
    auto hModule = LzCreateModule(hContext, hDevice, krn.data(), krn.size());
    return hModule;
}

inline ze_kernel_handle_t LzCreateKernel(ze_module_handle_t hModule, const char* kname)
{
    ze_kernel_desc_t kernelDesc = {ZE_STRUCTURE_TYPE_KERNEL_DESC, nullptr, 0, kname};
    ze_kernel_handle_t hKernel;
    L0_SAFE_CALL(zeKernelCreate(hModule, &kernelDesc, &hKernel));
    return hKernel;
}

inline std::tuple<ze_kernel_handle_t, ze_module_handle_t> LzCreateKernel(ze_context_handle_t hContext, ze_device_handle_t hDevice,
    const char *fn, const char* kname)
{
    ze_kernel_desc_t kernelDesc = {ZE_STRUCTURE_TYPE_KERNEL_DESC, nullptr, 0, kname};
    ze_kernel_handle_t hKernel;
    auto hModule = LzCreateModule(hContext, hDevice, fn);
    L0_SAFE_CALL(zeKernelCreate(hModule, &kernelDesc, &hKernel));
    return {hKernel, hModule};
}

// createKernel overload, which takes binary (or SPIRV) buffer (krn)
inline std::tuple<ze_kernel_handle_t, ze_module_handle_t> LzCreateKernel(ze_context_handle_t hContext, ze_device_handle_t hDevice,
                                       const uint8_t* krn, size_t krn_size, const char* kname)
{
    ze_kernel_desc_t kernelDesc = {ZE_STRUCTURE_TYPE_KERNEL_DESC, nullptr, 0, kname};
    auto hModule = LzCreateModule(hContext, hDevice, krn, krn_size);
    ze_kernel_handle_t hKernel;
    L0_SAFE_CALL(zeKernelCreate(hModule, &kernelDesc, &hKernel));
    return {hKernel, hModule};
}

inline void LzDestroyKernel(ze_kernel_handle_t hKernel)
{
    L0_SAFE_CALL(zeKernelDestroy(hKernel));
}

inline void LzSetGroupSize(ze_kernel_handle_t hKernel, const uint32_t group_size_x,
        const uint32_t group_size_y, const uint32_t group_size_z)
{
    L0_SAFE_CALL(zeKernelSetGroupSize(hKernel, group_size_x, group_size_y, group_size_z));
}

inline void LzAppendBarrier(ze_command_list_handle_t hCommandList)
{
    L0_SAFE_CALL(zeCommandListAppendBarrier(hCommandList, nullptr, 0, nullptr));
}

inline void LzAppendLaunchKernel(ze_command_list_handle_t hCommandList,
    ze_kernel_handle_t hKernel, ze_group_count_t *args,
    ze_event_handle_t hEvent = nullptr, unsigned numWait = 0,
    ze_event_handle_t *pWaitEvents = nullptr)
{
   L0_SAFE_CALL(zeCommandListAppendLaunchKernel(hCommandList, hKernel,
        args, hEvent, numWait, pWaitEvents));
}

inline void LzAppendLaunchKernelIndirect(ze_command_list_handle_t hCommandList,
    ze_kernel_handle_t hKernel, ze_group_count_t *args,
    ze_event_handle_t hEvent = nullptr, unsigned numWait = 0,
    ze_event_handle_t *pWaitEvents = nullptr)
{
   L0_SAFE_CALL(zeCommandListAppendLaunchKernelIndirect(hCommandList, hKernel,
        args, hEvent, numWait, pWaitEvents));
}

inline void LzAppendMemoryCopy(ze_command_list_handle_t hCommandList, void *dst,
    const void *src, size_t size, ze_event_handle_t hEvent = nullptr)
{
    L0_SAFE_CALL(zeCommandListAppendMemoryCopy(hCommandList, dst, src, size, hEvent, 0, nullptr));
}

inline void LzCopyToMemory(ze_command_list_handle_t hCommandList, void *dst, ze_image_handle_t src,
    ze_event_handle_t hEvent = nullptr)
{
    L0_SAFE_CALL(zeCommandListAppendImageCopyToMemory(hCommandList, dst, src, nullptr, hEvent, 0, nullptr));
}

inline void LzAppendMemoryFill(ze_command_list_handle_t hCommandList, void *ptr,
    const void *pattern, size_t pattern_size,  size_t size,
    ze_event_handle_t hEvent = nullptr, unsigned numWait = 0,
    ze_event_handle_t *pWaitEvents = nullptr)
{
    L0_SAFE_CALL(zeCommandListAppendMemoryFill(hCommandList, ptr, pattern, pattern_size, size,
                hEvent, numWait, pWaitEvents));
}

template<typename T>
void LzSetArgById(ze_kernel_handle_t hKernel, unsigned id, T *t)
{
    L0_SAFE_CALL(zeKernelSetArgumentValue(hKernel, id, sizeof(T), t));
}

template<typename T, typename Func>
void LzSetArg(ze_kernel_handle_t hKernel, Func get_id, T *t)
{
    LzSetArgById(hKernel, get_id(), t);
}

template <typename ... Args>
inline void LzSetKernelArgs(ze_kernel_handle_t hKernel, Args ... args)
{
    unsigned id = 0;
    auto get_id = [&](){ return id++;};
    (void)std::initializer_list<int>{(LzSetArg(hKernel, get_id, args),0)...};
}

inline void LzFenceCreate(ze_command_queue_handle_t hCommandQueue,
        ze_fence_handle_t &hFence)
{
    ze_fence_desc_t fence_desc = {
      ZE_STRUCTURE_TYPE_FENCE_DESC, nullptr, 0
    };

    L0_SAFE_CALL(zeFenceCreate(hCommandQueue, &fence_desc, &hFence));
}

inline void LzFenceDestroy(ze_fence_handle_t hFence)
{
    L0_SAFE_CALL(zeFenceDestroy(hFence));
}

//Busy wait check for completion of command list execution. High CPU utilization, low latency.
inline void LzExecute(ze_command_queue_handle_t hCommandQueue,
    ze_command_list_handle_t &hCommandList)
{
    L0_SAFE_CALL(zeCommandListClose(hCommandList));
    L0_SAFE_CALL(zeCommandQueueExecuteCommandLists(hCommandQueue, 1,
        &hCommandList, nullptr));
    L0_SAFE_CALL(zeCommandQueueSynchronize(hCommandQueue,
        std::numeric_limits<uint32_t>::max()));
}

//Poll for completion of command list execution. Sleep for specified time in between each poll.
//Low CPU utilization, higher latency.
inline void LzExecuteMinimumPoll(ze_command_queue_handle_t hCommandQueue,
    ze_command_list_handle_t &hCommandList, uint32_t sleepTime)
{
    ze_fence_handle_t fence;
    LzFenceCreate(hCommandQueue, fence);

    L0_SAFE_CALL(zeCommandListClose(hCommandList));
    L0_SAFE_CALL(zeCommandQueueExecuteCommandLists(hCommandQueue, 1,
        &hCommandList, fence));

    while (zeFenceQueryStatus(fence) != ZE_RESULT_SUCCESS)
    {
        std::this_thread::sleep_for(std::chrono::microseconds(sleepTime));
    }

    LzFenceDestroy(fence);
}

inline void LzWaitForEvent(ze_event_handle_t hEvent)
{
    L0_SAFE_CALL(zeEventHostSynchronize(hEvent,
                std::numeric_limits<uint32_t>::max()));
}

inline void LzSignalEvent(ze_event_handle_t hEvent)
{
    L0_SAFE_CALL(zeEventHostSignal(hEvent));
}

inline void LzReset(ze_command_list_handle_t hCommandList)
{
    L0_SAFE_CALL(zeCommandListReset(hCommandList));
}

inline void LzReset(ze_event_handle_t hEvent)
{
    L0_SAFE_CALL(zeEventHostReset(hEvent));
}

inline void LzAppendEventReset(ze_command_list_handle_t hCommandList, ze_event_handle_t hEvent)
{
    L0_SAFE_CALL(zeCommandListAppendEventReset(hCommandList, hEvent));
}

inline ze_event_pool_handle_t LzCreatePool(ze_context_handle_t hContext,
    ze_device_handle_t &hDevice, unsigned num = 1, unsigned count = 1)
{
    ze_event_pool_desc_t pool_desc = {
      ZE_STRUCTURE_TYPE_EVENT_POOL_DESC, nullptr,
      ZE_EVENT_POOL_FLAG_HOST_VISIBLE, count
    };

    ze_event_pool_handle_t hPool = nullptr;
    L0_SAFE_CALL(zeEventPoolCreate(hContext, &pool_desc, num, &hDevice, &hPool));
    return hPool;
}

inline ze_event_handle_t LzCreateEvent(ze_event_pool_handle_t hPool, unsigned index = 0)
{
    ze_event_desc_t desc = {ZE_STRUCTURE_TYPE_EVENT_DESC, nullptr, index, ZE_EVENT_SCOPE_FLAG_HOST, 0};

    ze_event_handle_t hEvent = nullptr;
    L0_SAFE_CALL(zeEventCreate(hPool, &desc, &hEvent));
    return hEvent;
}

inline void LzDestroyEvent(ze_event_handle_t hEvent)
{
    L0_SAFE_CALL(zeEventDestroy(hEvent));
}

inline ze_event_handle_t LzCreateEvent(ze_context_handle_t hContext, ze_device_handle_t &hDevice)
{
    return LzCreateEvent(LzCreatePool(hContext, hDevice));
}

#endif //L0_RT_HELPERS_H
