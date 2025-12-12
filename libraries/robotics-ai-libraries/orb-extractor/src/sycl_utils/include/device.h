// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#ifndef __DEVICE_H__
#define __DEVICE_H__

#ifdef WIN32
#ifdef SYCL_UTILS_EXPORTS
#define SYCL_UTILS_API __declspec(dllexport)
#else
#define SYCL_UTILS_API __declspec(dllimport)
#endif
#else
#define SYCL_UTILS_API
#endif

#include <stdint.h>

#include <bitset>
#include <cstddef>
#include <functional>
#include <memory>
#include <mutex>
#include <queue>

#define MAX_DEVICES 16

enum MemoryType
{
  SHARED_MEMORY,
  DEVICE_MEMORY,
  HOST_MEMORY
};

enum DeviceType
{
  DEFAULT,
  CPU,
  INTEGRATED_GPU,
  DISCRETE_GPU
};

enum StorageOrder
{
  COLUMN_MAJOR,
  ROW_MAJOR,
};

struct Rect
{
  int x;
  int y;
  uint32_t width;
  uint32_t height;

  Rect() {}

  Rect(int _x, int _y, uint32_t _width, uint32_t _height)
  {
    x = _x;
    y = _y;
    width = _width;
    height = _height;
  }

  Rect(int _x, int _y, int _width, int _height)
  {
    x = _x;
    y = _y;
    width = (uint32_t)_width;
    height = (uint32_t)_height;
  }
};

struct Size
{
  uint32_t width;
  uint32_t height;
};

struct DeviceEvent;

class DeviceImpl;

class DeviceSlotQueue
{
public:
  DeviceSlotQueue() = default;

  ~DeviceSlotQueue() { int a = 0; }

  size_t Allocate();

  void Deallocate(size_t slotIndex);

  bool IsSlotFree(size_t slot) const;

  size_t AvailableSlots() const;

private:
  static std::bitset<MAX_DEVICES> occupied_slots;
  static std::array<size_t, MAX_DEVICES> slot_array;
  static bool initialized;
  static std::mutex mutex;

  static void Initialize();
  static std::queue<size_t> & GetFreeSlots()
  {
    static std::queue<size_t> free_slots(std::deque<size_t>(slot_array.begin(), slot_array.end()));
    return free_slots;
  }
};

class SYCL_UTILS_API Device
{
public:
  using Ptr = std::shared_ptr<Device>;

  Device();

  Device(DeviceType type);

  Device(DeviceType type, int index);

  ~Device();

  void GetDeviceName();

  int GetDeviceIndex();

  bool SetType(DeviceType type);

  /* Internal used only */
  DeviceImpl * GetDeviceImpl();

  static Device::Ptr getDefaultDevice(int index);

  static void cleanup(int index);

  bool IsGPU();

  bool IsCPU();

private:
  Device(const Device &) = delete;
  Device & operator=(const Device &) = delete;

  DeviceType type_;

  DeviceImpl * devImpl_;

  int devId_;

  DeviceSlotQueue global_slots;
};

#endif  // DEVICE_H
