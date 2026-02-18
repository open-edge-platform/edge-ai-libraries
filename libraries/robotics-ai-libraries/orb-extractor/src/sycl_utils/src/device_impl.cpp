// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include "device_impl.h"

#include <iostream>

DeviceImpl::DeviceImpl(DeviceType type)
{
  switch (type) {
    case DEFAULT:
      q_ = new sycl::queue{sycl::property::queue::in_order{}};
      break;
    case CPU:
      q_ = new sycl::queue{sycl::cpu_selector_v};
      break;
    case INTEGRATED_GPU:
      q_ = new sycl::queue{sycl::gpu_selector_v};
      break;
    case DISCRETE_GPU:
      q_ = new sycl::queue{sycl::gpu_selector_v};
      break;
    default:
      std::cerr << "Unsupported device\n";
  }
}

DeviceImpl::~DeviceImpl() { std::cout << "DeviceImpl clean up\n"; }

void DeviceImpl::get_device_name()
{
  std::cout << "Running on device: " << q_->get_device().get_info<sycl::info::device::name>()
            << "\n";
}

size_t DeviceImpl::get_global_mem_size()
{
  return q_->get_device().get_info<sycl::info::device::global_mem_size>();
}

void * DeviceImpl::malloc_shared(std::size_t size)
{
  if (size > 0)
    return sycl::malloc_shared(size, *q_);
  else
    return nullptr;
}

void * DeviceImpl::malloc_device(std::size_t size)
{
  if (size > 0)
    return sycl::malloc_device(size, *q_);
  else
    return nullptr;
}

void * DeviceImpl::malloc_host(std::size_t size)
{
  if (size > 0)
    return sycl::malloc_host(size, *q_);
  else
    return nullptr;
}

void DeviceImpl::free(void * data)
{
  if (data != nullptr) sycl::free(data, *q_);
}

void DeviceImpl::memset(void * dst, int value, std::size_t size)
{
  if (dst == nullptr) throw std::runtime_error("Nullptr for memory access");

  q_->memset(dst, value, size).wait_and_throw();
}

void DeviceImpl::memcpy(void * dst, const void * src, std::size_t size)
{
  if ((dst == nullptr) || (src == nullptr)) throw std::runtime_error("Nullptr for memory access");
  q_->memcpy(dst, src, size).wait_and_throw();
}

void DeviceImpl::memcpy(
  void * dst, const void * src, std::size_t major, std::size_t minor, std::size_t src_pitch,
  std::size_t dst_pitch)
{
  if ((dst == nullptr) || (src == nullptr)) throw std::runtime_error("Nullptr for memory access");

  for (int i = 0; i < minor; i++) {
    int src_offset, dst_offset;

    src_offset = i * src_pitch;
    dst_offset = i * dst_pitch;

    std::memcpy((void *)((char *)dst + dst_offset), (void *)((char *)src + src_offset), major);
  }
}

sycl::event DeviceImpl::memcpy_async(void * dst, const void * src, std::size_t size)
{
  if ((dst == nullptr) || (src == nullptr)) throw std::runtime_error("Nullptr for memory access");
  sycl::event event = q_->memcpy(dst, src, size);
  return event;
}

template <typename A>
void DeviceImpl::fill(void * dst, A pattern, std::size_t size)
{
  if (dst == nullptr) throw std::runtime_error("Nullptr for memory access");
  q_->fill(dst, pattern, size).wait_and_throw();
}

template <typename A>
sycl::event DeviceImpl::fill_async(void * dst, A pattern, std::size_t size)
{
  if (dst == nullptr) throw std::runtime_error("Nullptr for memory access");

  sycl::event event = q_->fill(dst, pattern, size);
  return event;
}

template <typename Func>
void DeviceImpl::submit(Func lambda)
{
  q_->submit(lambda);
}

void DeviceImpl::wait() { q_->wait_and_throw(); }

sycl::queue * DeviceImpl::get_queue() { return q_; }

// explict initialize
template sycl::event DeviceImpl::fill_async(void * dst, float pattern, std::size_t size);
template sycl::event DeviceImpl::fill_async(void * dst, double pattern, std::size_t size);
template sycl::event DeviceImpl::fill_async(void * dst, int pattern, std::size_t size);
template sycl::event DeviceImpl::fill_async(void * dst, char pattern, std::size_t size);
template sycl::event DeviceImpl::fill_async(void * dst, unsigned char pattern, std::size_t size);
template sycl::event DeviceImpl::fill_async(void * dst, short pattern, std::size_t size);
template sycl::event DeviceImpl::fill_async(void * dst, unsigned short pattern, std::size_t size);
template sycl::event DeviceImpl::fill_async(void * dst, bool pattern, std::size_t size);

template void DeviceImpl::fill(void * dst, float pattern, std::size_t size);
template void DeviceImpl::fill(void * dst, double pattern, std::size_t size);
template void DeviceImpl::fill(void * dst, char pattern, std::size_t size);
template void DeviceImpl::fill(void * dst, unsigned char pattern, std::size_t size);
template void DeviceImpl::fill(void * dst, int pattern, std::size_t size);
template void DeviceImpl::fill(void * dst, short pattern, std::size_t size);
template void DeviceImpl::fill(void * dst, unsigned short pattern, std::size_t size);
template void DeviceImpl::fill(void * dst, bool pattern, std::size_t size);
