// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __CM_BASE_H__
#define __CM_BASE_H__

#include <memory>
#include <vector>
#include <unordered_map>
#include <functional>

#include "device_base.h"

#include "l0_rt_helpers.h"

namespace gpu
{

enum InterpolationType
{
    kInterpolationLinear,
    kInterpolationNearest,
    kInterpolationCubic,
    kInterpolationArea
};

enum MemoryType
{
    kHostMemory = 0x0,
    kDeviceMemory = 0x1,
    kSharedMemory = 0x2
};

inline MemoryType operator | (MemoryType a, MemoryType b)
{
    return static_cast<MemoryType>(static_cast<int>(a) | static_cast<int>(b));
}

inline MemoryType operator & (MemoryType a, MemoryType b)
{
    return static_cast<MemoryType>(static_cast<int>(a) & static_cast<int>(b));
}

enum KernelType
{
    kDirectKernel,
    kIndirectKernel,
    kCooperativeKernel
};

enum OrbKernelType
{
    kResize,
    kGaussian,
    kFast,
    kFastNMS,
    kMemset,
    kOrbDescriptor
};

class KernelBase;

struct KernelNode
{
    ze_kernel_handle_t      kernel;
    ze_module_handle_t      module;
    ze_event_handle_t       event;
    ze_event_handle_t       host_event;
    ze_event_handle_t       wait_event;
    CommandListIndex        command_list_index;
    ze_group_count_t        group_count;
    ze_group_count_t        *p_group_count;
    std::vector<void *>     input_surface;
    std::vector<void *>     output_surface;
    KernelType              kernel_type;
    OrbKernelType           orb_type;

};


class CmBase
{
public:

    using Ptr = std::shared_ptr<CmBase>;

    CmBase();

    ~CmBase(void);

    void CreateGraph(int command_list_count = 1);

    void AddKernelToGraph(KernelNode &kernel, KernelType kernel_type);

    void ExecuteGraph(CommandListIndex index);

    void AddToGlobalBuffer(void *addr);

    void RemoveFromGlobalBuffer(void *addr);

    ze_event_handle_t CreateEvent();

    void AppendAction(CommandListIndex cmd_idx, ze_event_handle_t event, EventAction::Ptr action,
       int slot);

    void AppendResetEvent(CommandListIndex cmd_idx, ze_event_handle_t event);

    void DestroyEvent(ze_event_handle_t event);

    bool IsEventExist(ze_event_handle_t event);

    void SetKernelPath(std::string path);

    std::string GetKernelPath();

    ze_context_handle_t GetContext();

    ze_device_handle_t GetDevice();

    DeviceBase *GetDeviceBase();


private:

    ze_device_handle_t device_;
    ze_context_handle_t context_;
    ze_command_queue_handle_t command_queue_;
    std::vector<ze_command_list_handle_t> *command_list_;
    std::string kernel_file_path_;
    EventActionType *event_action_;
    EventArrayType *event_array_;

    DeviceBase* device_base_;


};

} // namespace gpu

#endif // !__CM_BASE_H__

