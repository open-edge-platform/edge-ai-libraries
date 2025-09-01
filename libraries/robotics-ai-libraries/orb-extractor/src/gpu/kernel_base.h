// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __KERNEL_BASE_H__
#define __KERNEL_BASE_H__

#include "cm_base.h"
#include "device_buffer.h"
#include "device_image.h"
#include "l0_rt_helpers.h"
#include <filesystem>

namespace gpu
{

class KernelBase
{
public:

    using Ptr = std::shared_ptr<KernelBase>;

    static Ptr New(OrbKernelType orb_type, CmBase::Ptr baseObj)
    {
        return std::make_shared<KernelBase>(orb_type, baseObj);
    }

    KernelBase() = delete;

    KernelBase(OrbKernelType type, CmBase::Ptr baseObj)
    {
        gpuDev_ = std::move(baseObj);

        kernel_node_.command_list_index = kAppend;
        kernel_node_.event = nullptr;
        kernel_node_.host_event = nullptr;
        kernel_node_.wait_event = nullptr;
        kernel_param_count_ = 0;
        kernel_node_.kernel_type = kDirectKernel;
        kernel_node_.orb_type = type;
        kernel_node_.p_group_count = 0;
        kernel_node_.kernel = nullptr;
        kernel_node_.module = nullptr;

    }

    ~KernelBase() {
        LzDestroyKernel(kernel_node_.kernel);
        LzDestroy(kernel_node_.module);
    }

    void LoadKernel(const char *binary_name, const char *kernel_name)
    {
        std::string binary_name_(binary_name);
        std::string binary_path = gpuDev_->GetKernelPath().append("/").append(binary_name_);

        if (std::filesystem::exists(binary_path)) {
            auto [kernel, module] = LzCreateKernel(gpuDev_->GetContext(), gpuDev_->GetDevice(),
                binary_path.c_str(), kernel_name);
            kernel_node_.kernel = kernel;
            kernel_node_.module = module;
        } else {
            std::cout << "GPU kernel binary path " << binary_path << " is not valid" << std::endl;
            exit(1);
        }
    }

    void SetCommandListIndex(CommandListIndex idx)
    {
        kernel_node_.command_list_index = idx;
    }

    void SetGroupCount(const uint32_t gx, const uint32_t gy, const uint32_t gz)
    {
        kernel_node_.group_count = {gx, gy, gz};
    }

    void SetGroupCount(ze_group_count_t *group_count)
    {
        kernel_node_.p_group_count = group_count;
    }

    void SetGroupSize(const uint32_t group_size_x, const uint32_t group_size_y,
            const uint32_t group_size_z)
    {
        if (kernel_node_.kernel != nullptr)
            LzSetGroupSize(kernel_node_.kernel, group_size_x, group_size_y, group_size_z);
    }

    void AddInputSurface(void *input_surface)
    {
        kernel_node_.input_surface.push_back(input_surface);
    }

    void AddOutputSurface(void *output_surface)
    {
        kernel_node_.output_surface.push_back(output_surface);
    }

    void *GetInputSurface(uint32_t index)
    {
        if (index < kernel_node_.input_surface.size())
            return kernel_node_.input_surface.at(index);
        else
            return nullptr;
    }

    void *GetOutputSurface(uint32_t index)
    {
        void *surface_ptr = nullptr;

        if (index < kernel_node_.output_surface.size())
            surface_ptr = kernel_node_.output_surface.at(index);

        return surface_ptr;
    }

    template<typename T>
    void SetArgs(T *in)
    {
        LzSetArgById(kernel_node_.kernel, kernel_param_count_++, in);
    }

    template<typename T>
    void SetArgs(T *in, int id)
    {
        LzSetArgById(kernel_node_.kernel, id, in);
    }

    KernelNode getKernel()
    {
        return kernel_node_;
    }

    void SubmitKernel(KernelType kernel_type = kDirectKernel)
    {
        gpuDev_->AddKernelToGraph(kernel_node_, kernel_type);
    }

    void AppendAction(ze_event_handle_t event, EventAction::Ptr action, int slot=0)
    {
        gpuDev_->AppendAction(kernel_node_.command_list_index, event, std::move(action), slot);
    }

    void AppendResetEvent(ze_event_handle_t event)
    {
        gpuDev_->AppendResetEvent(kernel_node_.command_list_index, event);
    }

    ze_event_handle_t GetEvent()
    {
        ze_event_handle_t event;

        if (kernel_node_.event == nullptr)
        {
            event = gpuDev_->CreateEvent();
            kernel_node_.event = event;
        }
        else
        {
            if (gpuDev_->IsEventExist(kernel_node_.event))
            {
                event = kernel_node_.event;
            }
            else
            {
                event = gpuDev_->CreateEvent();
                kernel_node_.event = event;
            }
        }

        return event;
    }

    ze_event_handle_t GetHostEvent()
    {
        ze_event_handle_t event;

        if (kernel_node_.host_event == nullptr)
        {
            event = gpuDev_->CreateEvent();
            kernel_node_.host_event = event;
        }
        else
        {
            if (gpuDev_->IsEventExist(kernel_node_.host_event))
            {
                event = kernel_node_.host_event;
            }
            else
            {
                event = gpuDev_->CreateEvent();
                kernel_node_.host_event = event;
            }
        }

        return event;
    }

    void AddHostEventToKernel(ze_event_handle_t event)
    {
        kernel_node_.host_event = event;
    }

    void AddEventToKernel(ze_event_handle_t event)
    {
        kernel_node_.event = event;
    }

    void AddWaitEvent(ze_event_handle_t event)
    {
        kernel_node_.wait_event = event;
    }

    void SetKernelType(KernelType type)
    {
        kernel_node_.kernel_type = type;
    }

    KernelType GetKernelType()
    {
        return kernel_node_.kernel_type;
    }

    int divUp(int total, int grain)
    {
        return (total + grain - 1) / grain;
    }

    virtual void Submit() {}

protected:
    CmBase::Ptr gpuDev_;

private:
    KernelNode  kernel_node_;
    uint        kernel_param_count_;
};


} // namespace gpu

#endif // !__KERNEL_BASE_H__


