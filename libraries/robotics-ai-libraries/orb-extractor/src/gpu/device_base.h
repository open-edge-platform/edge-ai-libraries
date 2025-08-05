// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __DEVICE_BASE_H__
#define __DEVICE_BASE_H__

#include <memory>
#include "l0_rt_helpers.h"

namespace gpu
{
constexpr static uint32_t g_maximum_events = 50;

enum CommandListIndex
{
    kImmediate = 0, //Immediate submission of command
    kAppend = 1, //Append commands into queue
    //Command queue priorities. Lower the value, higher the priority.
    kCmdList0 = 1,
    kCmdList1 = 2,
};

class EventAction {
public:

    using Ptr = std::shared_ptr<EventAction>;

    EventAction() : persistent_(0) {}

    EventAction(bool persistent) : persistent_(persistent) {}

    ~EventAction() {}

    template<typename F, typename... Args>
    void BindAction(const ze_event_handle_t event, F func, Args... args)
    {
        actions_.emplace(
            event,
            [func, args...] () mutable { return std::invoke(func, args...); }
            );

    }

    void call(const ze_event_handle_t event)
    {
        actions_[event]();
    }

    bool isPersistent()
    {
        return persistent_;
    }

private:
    std::unordered_map<ze_event_handle_t, std::function<void()>> actions_;
    bool persistent_;
};

using EventActionType = std::vector<std::vector<std::unordered_map<ze_event_handle_t, EventAction::Ptr>>>;
using EventArrayType = std::array<ze_event_handle_t, g_maximum_events>;

class DeviceBase
{
public:

  void AddRef()
  {
    refcnt++;
  }

  bool DelRef()
  {
    bool last_ref = false;
    refcnt--;

    if (refcnt == 0)
    {
      DestroyInstance();
      last_ref = true;
    }

    return last_ref;
  }

  void DestroyInstance()
  {
    if (refcnt == 0)
    {
      for (auto & item : command_list_)
        LzDestroy(item);

      for (auto & item : event_array_)
      {
        if (item != nullptr)
          LzDestroyEvent(item);
      }

      LzDestroy(event_pool_);
      LzDestroy(command_queue_);
      LzDestroy(context_);
    }
  }

  DeviceBase()
  {
    auto [driver, device, context] = LzFindDriverAndDevice();

    driver_ = driver;
    device_ = device;
    context_ = context;

    event_pool_ = LzCreatePool(context_, device_, 1, g_maximum_events);
    device_properties_ = LzGetDeviceProperties(device_);

    event_array_.fill(nullptr);
    refcnt = 0;
    graph_initialized_ = false;
    command_queue_ = 0;
  };

  ~DeviceBase(void)
  {
  }

  std::vector<ze_command_list_handle_t> * CreateCommandList(int count)
  {
    command_list_.push_back(LzCreateImmCommandList(context_, device_));

    for (int i = 0; i < count; i++)
        command_list_.push_back(LzCreateCommandList(context_, device_));

    graph_initialized_ = true;
    return &command_list_;
  }

  std::vector<ze_command_list_handle_t> * GetCommandList()
  {
    return &command_list_;
  }

  ze_command_queue_handle_t CreateCommandQueue(void)
  {
    command_queue_ = LzCreateCommandQueue(context_, device_);
    return command_queue_;
  }

  EventActionType * CreateEventAction(int command_count)
  {
    event_action_.resize(command_count);
    return &event_action_;
  }

  ze_context_handle_t GetContext()
  {
    return context_;
  }

  ze_device_handle_t GetDevice()
  {
    return device_;
  }

  EventActionType* GetEventAction()
  {
    return &event_action_;
  }

  EventArrayType* GetEventArray()
  {
    return &event_array_;
  }

  ze_event_handle_t CreateEvent()
  {
    ze_event_handle_t *empty_slot = std::find(std::begin(event_array_), std::end(event_array_),
            nullptr);
    int event_index = 0;

    if (empty_slot != std::end(event_array_))
    {
        event_index = std::distance(event_array_.data(), empty_slot);
    }
    else
    {
        throw std::runtime_error("All events are fully used. Increase the event pool");
    }

    ze_event_handle_t event  = LzCreateEvent(event_pool_, event_index);

    LzReset(event);
    event_array_[event_index] = event;

    return event;
  }

  void DestroyEvent(ze_event_handle_t event)
  {
    ze_event_handle_t *event_slot = std::find(std::begin(event_array_), std::end(event_array_),
            event);
    int event_index = 0;

    if (event_slot != std::end(event_array_))
    {
        event_index = std::distance(event_array_.data(), event_slot);
    }
    else
    {
        throw std::runtime_error("Double free event");
    }

    event_array_[event_index] = nullptr;

    LzReset(event);
    LzDestroyEvent(event);
  }

  bool IsEventExist(ze_event_handle_t event)
  {
    ze_event_handle_t *event_slot = std::find(std::begin(event_array_), std::end(event_array_),
            event);

    bool event_found = false;

    if (event_slot != std::end(event_array_))
    {
        event_found = true;
    }

    return event_found;
  }

  void AppendAction(CommandListIndex cmd_idx, ze_event_handle_t event,
        EventAction::Ptr action, int slot)
  {
      event_action_.at(cmd_idx).push_back({{event, action}});
  }

  bool isGraphInitialized()
  {
    return graph_initialized_;
  }



private:
  ze_driver_handle_t driver_;
  ze_device_handle_t device_;
  ze_context_handle_t context_;
  ze_event_pool_handle_t event_pool_;
  ze_command_queue_handle_t command_queue_;
  ze_device_properties_t device_properties_;
  std::vector<ze_command_list_handle_t> command_list_;
  EventActionType event_action_;
  EventArrayType event_array_;

  int refcnt;

  bool graph_initialized_;
};

} // namespace gpu

#endif
