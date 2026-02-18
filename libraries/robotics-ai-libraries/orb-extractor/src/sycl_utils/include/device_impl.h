// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#ifndef __DEVICE_IMPL_H__
#define __DEVICE_IMPL_H__

#include <dpct/dpct.hpp>
#include <sycl/sycl.hpp>

#include "device.h"

namespace intelext = sycl::ext::oneapi::experimental;
#define __device_inline__ __inline__ __attribute__((always_inline))

template <typename T1, typename T2>
static inline T1 divUp(const T1 total, const T2 grain)
{
  return (total + grain - 1) / grain;
}

template <typename T1, typename T2>
static inline T1 align(const T1 total, const T2 grain)
{
  return divUp(total, grain) * grain;
}

// using namespace sycl; // Removed to fix SYCL 2025.0 ambiguity with Ubuntu 24.04

struct SYCL_UTILS_API DeviceEvent
{
  using Ptr = std::shared_ptr<DeviceEvent>;

  static Ptr create() { return std::make_shared<DeviceEvent>(); }

  DeviceEvent() = default;
  ~DeviceEvent() = default;

  void add(sycl::event event) { events.push_back(event); }

  DeviceEvent(const DeviceEvent & other) { this->events = other.events; }

  DeviceEvent(DeviceEvent && other) noexcept { this->events = std::move(other.events); }

  std::vector<sycl::event> events;
};

class SYCL_UTILS_API DeviceImpl
{
public:
  DeviceImpl() = delete;

  DeviceImpl(DeviceType type);

  ~DeviceImpl();

  void get_device_name();

  size_t get_global_mem_size();

  void * malloc_shared(std::size_t size);

  void * malloc_device(std::size_t size);

  void * malloc_host(std::size_t size);

  void free(void * data);

  void memset(void * dst, int value, std::size_t size);

  void memcpy(void * dst, const void * src, std::size_t size);

  void memcpy(
    void * dst, const void * src, std::size_t major, std::size_t minor, std::size_t src_pitch,
    std::size_t dst_pitch);

  sycl::event memcpy_async(void * dst, const void * src, std::size_t size);

  template <typename A>
  void fill(void * dst, A pattern, std::size_t size);

  template <typename A>
  sycl::event fill_async(void * dst, A pattern, std::size_t size);

  template <typename Func>
  void submit(Func lambda);

  void wait();

  sycl::queue * get_queue();

private:
  sycl::queue * q_;
};

#endif
