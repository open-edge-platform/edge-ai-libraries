// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include "device.h"

#include "device_impl.h"

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

Device::Device() : type_(DEFAULT)
{
  devImpl_ = new DeviceImpl(type_);
  if (global_slots.AvailableSlots()) devId_ = global_slots.Allocate();
}

Device::Device(DeviceType type) : type_(type)
{
  devImpl_ = new DeviceImpl(type);
  if (global_slots.AvailableSlots()) devId_ = global_slots.Allocate();
}

Device::Device(DeviceType type, int index) : type_(type), devId_(index)
{
  devImpl_ = new DeviceImpl(type);
}

Device::~Device()
{
  global_slots.Deallocate(devId_);
  // std::cout << "\n";
}

void Device::GetDeviceName() { devImpl_->get_device_name(); }

int Device::GetDeviceIndex() { return devId_; }

DeviceImpl * Device::GetDeviceImpl() { return devImpl_; }

bool Device::IsGPU() { return 0; }

bool Device::IsCPU() { return 0; }
