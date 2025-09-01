// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "cm_base.h"
#include <thread>
#include <functional>
#include <chrono>

namespace gpu
{


static std::string                  g_kernel_path;

void DestroyEventCallback(ze_event_handle_t event, EventArrayType *event_array)
{
    ze_event_handle_t *event_slot = std::find(event_array->begin(), event_array->end(),
            event);
    int event_index = 0;

    if (event_slot != event_array->end())
    {
        event_index = std::distance(event_array->data(), event_slot);
    }
    else
    {
        throw std::runtime_error("Double free event");
    }

    (*event_array)[event_index] = nullptr;

    LzReset(event);
    LzDestroyEvent(event);
}

void gpu_event_handler(CommandListIndex cmd_idx, int sleep_time,
    EventActionType *event_action, EventArrayType * event_array)
{
  int slot = event_action->at(cmd_idx).size();

  for (int i = 0; i < slot; i++)
  {
     for (auto &e : event_action->at(cmd_idx).at(i))
     {
        while (zeEventQueryStatus(e.first) != ZE_RESULT_SUCCESS)
       {
         std::this_thread::sleep_for(std::chrono::microseconds(sleep_time));
       }

       EventAction::Ptr action = event_action->at(cmd_idx).at(i)[e.first];
       action->call(e.first);
       DestroyEventCallback(e.first, event_array);
     }
  }
}


template<typename T>
bool remove_from_global_list(T item, std::vector<T> &list)
{
    bool found = false;

    typename std::vector<T>::iterator it =  std::find(list.begin(), list.end(), item);

    if (it != list.end())
    {
        list.erase(it);
        found = true;
    }

    return found;
}


CmBase::CmBase()
{
    device_base_ = new DeviceBase();
    device_ = device_base_->GetDevice();
    context_ = device_base_->GetContext();
    event_array_ = device_base_->GetEventArray();
    command_list_ = nullptr;
    command_queue_ = 0;
    event_action_ = nullptr;

    device_base_->AddRef();
    if (device_base_->isGraphInitialized())
        command_list_ = device_base_->GetCommandList();
}

CmBase::~CmBase(void)
{
    if (device_base_->DelRef())
      delete device_base_;
}

void CmBase::CreateGraph(int command_list_count)
{

    command_list_ = device_base_->CreateCommandList(command_list_count);

    command_queue_ = device_base_->CreateCommandQueue();

    event_action_ = device_base_->CreateEventAction(command_list_count);
}


void CmBase::ExecuteGraph(CommandListIndex index)
{
    int sleep_time = 1;
    if(const char* env_sleep = std::getenv("CPU_SLEEP_TIME")) {
      sleep_time = atoi(env_sleep);
    }

    ze_command_list_handle_t cmd_list = command_list_->at(index);

    std::thread event_thread(gpu_event_handler, index, sleep_time,
        std::ref(event_action_), std::ref(event_array_));

    LzExecuteMinimumPoll(command_queue_, cmd_list, sleep_time);

    event_thread.join();

    event_action_->at(index).clear();

    // Reset command list
    LzReset(cmd_list);
}

void CmBase::AppendResetEvent(CommandListIndex cmd_idx, ze_event_handle_t event)
{
    ze_command_list_handle_t cmd_list = command_list_->at(cmd_idx);

    LzAppendEventReset(cmd_list, event);
}

void CmBase::AppendAction(CommandListIndex cmd_idx, ze_event_handle_t event,
        EventAction::Ptr action, int slot)
{
    return device_base_->AppendAction(cmd_idx, event, std::move(action), slot);
}

ze_event_handle_t CmBase::CreateEvent()
{
    return device_base_->CreateEvent();
}

bool CmBase::IsEventExist(ze_event_handle_t event)
{
    return device_base_->IsEventExist(event);
}

void CmBase::DestroyEvent(ze_event_handle_t event)
{
    device_base_->DestroyEvent(event);
}

void CmBase::AddKernelToGraph(KernelNode &kernel, KernelType kernel_type)
{
    ze_command_list_handle_t cmd_list = command_list_->at(kernel.command_list_index);

    uint32_t wait_event_count = 0;

    if (kernel.wait_event != nullptr) wait_event_count = 1;

    switch (kernel_type)
    {
    case kDirectKernel:
        LzAppendLaunchKernel(cmd_list, kernel.kernel, &kernel.group_count,
                kernel.event, wait_event_count, &kernel.wait_event);
        break;
    case kIndirectKernel:
        LzAppendLaunchKernelIndirect(cmd_list, kernel.kernel, kernel.p_group_count,
                kernel.event, wait_event_count, &kernel.wait_event);
        break;
    default:
        break;
    }

    LzAppendBarrier(cmd_list);
}


void CmBase::SetKernelPath(std::string path)
{
    g_kernel_path = std::move(path);
}

std::string CmBase::GetKernelPath()
{
    return g_kernel_path;
}

ze_context_handle_t CmBase::GetContext()
{
    return context_;
}

ze_device_handle_t CmBase::GetDevice()
{
    return device_;
}

DeviceBase * CmBase::GetDeviceBase()
{
    return device_base_;
}

} // namespace gpu

