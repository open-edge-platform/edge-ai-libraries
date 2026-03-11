// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include "device.h"

#include <cstdlib>
#include <iostream>

#include "device_impl.h"

// Debug macro - enabled by GPU_MEM_DEBUG=1 environment variable
static bool gpu_device_debug_enabled()
{
  static int enabled = -1;
  if (enabled < 0) {
    const char * env = std::getenv("GPU_MEM_DEBUG");
    enabled = (env && (std::string(env) == "1" || std::string(env) == "true")) ? 1 : 0;
  }
  return enabled == 1;
}

#define GPU_DEV_DEBUG(fmt, ...)                              \
  do {                                                       \
    if (gpu_device_debug_enabled()) {                        \
      fprintf(stderr, "[GPU_DEV] " fmt "\n", ##__VA_ARGS__); \
      fflush(stderr);                                        \
    }                                                        \
  } while (0)

// Sentinel value to indicate devId_ was never allocated
static constexpr int DEVICE_ID_NOT_ALLOCATED = -1;

std::bitset<MAX_DEVICES> DeviceSlotQueue::occupied_slots;
bool DeviceSlotQueue::initialized = false;
std::mutex DeviceSlotQueue::mutex;
std::array<size_t, MAX_DEVICES> DeviceSlotQueue::slot_array = []() {
  std::array<size_t, MAX_DEVICES> arr;
  for (size_t i = 0; i < MAX_DEVICES; ++i) {
    arr[i] = i;
  }
  return arr;
}();

size_t DeviceSlotQueue::Allocate()
{
  std::lock_guard<std::mutex> lock(mutex);
  auto & free_slots = GetFreeSlots();
  if (free_slots.empty()) {
    throw std::runtime_error("No more free slots to create device");
  }
  size_t slot = free_slots.front();
  free_slots.pop();
  occupied_slots.set(slot);
  return slot;
}

void DeviceSlotQueue::Deallocate(size_t slot)
{
  std::lock_guard<std::mutex> lock(mutex);
  if (slot >= MAX_DEVICES) {
    throw std::out_of_range("Invalid slot number");
  }
  if (!occupied_slots.test(slot)) {
    throw std::runtime_error("Slot is already free");
  }
  occupied_slots.reset(slot);
  GetFreeSlots().push(slot);
}

bool DeviceSlotQueue::IsSlotFree(size_t slot) const
{
  std::lock_guard<std::mutex> lock(mutex);
  if (slot >= MAX_DEVICES) {
    throw std::out_of_range("Invalid slot number");
  }
  return !occupied_slots.test(slot);
}

size_t DeviceSlotQueue::AvailableSlots() const
{
  std::lock_guard<std::mutex> lock(mutex);
  return GetFreeSlots().size();
}

Device::Device() : type_(DEFAULT), devId_(DEVICE_ID_NOT_ALLOCATED)
{
  GPU_DEV_DEBUG("Device() CTOR START: this=%p", (void *)this);
  devImpl_ = new DeviceImpl(type_);
  if (global_slots.AvailableSlots()) {
    devId_ = global_slots.Allocate();
    GPU_DEV_DEBUG("Device() CTOR: allocated slot devId_=%d", devId_);
  } else {
    GPU_DEV_DEBUG("Device() CTOR WARNING: no slots available, devId_ remains %d", devId_);
  }
  GPU_DEV_DEBUG("Device() CTOR END: this=%p, devId_=%d", (void *)this, devId_);
}

Device::Device(DeviceType type) : type_(type), devId_(DEVICE_ID_NOT_ALLOCATED)
{
  GPU_DEV_DEBUG("Device(type=%d) CTOR START: this=%p", (int)type, (void *)this);
  devImpl_ = new DeviceImpl(type);
  if (global_slots.AvailableSlots()) {
    devId_ = global_slots.Allocate();
    GPU_DEV_DEBUG("Device(type) CTOR: allocated slot devId_=%d", devId_);
  } else {
    GPU_DEV_DEBUG("Device(type) CTOR WARNING: no slots available, devId_ remains %d", devId_);
  }
  GPU_DEV_DEBUG("Device(type) CTOR END: this=%p, devId_=%d", (void *)this, devId_);
}

Device::Device(DeviceType type, int index) : type_(type), devId_(index)
{
  GPU_DEV_DEBUG("Device(type=%d, index=%d) CTOR: this=%p", (int)type, index, (void *)this);
  devImpl_ = new DeviceImpl(type);
}

Device::~Device()
{
  GPU_DEV_DEBUG("~Device() DTOR START: this=%p, devId_=%d", (void *)this, devId_);
  if (devId_ != DEVICE_ID_NOT_ALLOCATED && devId_ >= 0 && devId_ < MAX_DEVICES) {
    GPU_DEV_DEBUG("~Device() DTOR: deallocating slot %d", devId_);
    global_slots.Deallocate(devId_);
  } else {
    GPU_DEV_DEBUG("~Device() DTOR: skipping deallocation (devId_=%d)", devId_);
  }
  if (devImpl_) {
    delete devImpl_;
    devImpl_ = nullptr;
  }
  GPU_DEV_DEBUG("~Device() DTOR END: this=%p", (void *)this);
}

void Device::GetDeviceName() { devImpl_->get_device_name(); }

int Device::GetDeviceIndex() { return devId_; }

DeviceImpl * Device::GetDeviceImpl() { return devImpl_; }

bool Device::IsGPU() { return 0; }

bool Device::IsCPU() { return 0; }
