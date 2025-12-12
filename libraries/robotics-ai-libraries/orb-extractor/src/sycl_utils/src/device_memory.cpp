// SPDX-License-Identifier: BSD-3-Clause
/*
 * Software License Agreement (BSD License)
 *
 *  Copyright (c) 2011, Willow Garage, Inc.
 *  All rights reserved.
 *
 *  Redistribution and use in source and binary forms, with or without
 *  modification, are permitted provided that the following conditions
 *  are met:
 *
 *   * Redistributions of source code must retain the above copyright
 *     notice, this list of conditions and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above
 *     copyright notice, this list of conditions and the following
 *     disclaimer in the documentation and/or other materials provided
 *     with the distribution.
 *   * Neither the name of Willow Garage, Inc. nor the names of its
 *     contributors may be used to endorse or promote products derived
 *     from this software without specific prior written permission.
 *
 *  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 *  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 *  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 *  FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 *  COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 *  INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 *  BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 *  LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 *  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 *  LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 *  ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 *  POSSIBILITY OF SUCH DAMAGE.
 *
 *  Author: Anatoly Baskeheev, Itseez Ltd, (myname.mysurname@mycompany.com)
 */

#ifndef __DEVICE_MEMORY_IMPL__
#define __DEVICE_MEMORY_IMPL__
#include "device_memory.h"

#include "device_impl.h"
#include "dpct/dpct.hpp"
#include "gpu_memory_manager.h"

thread_local std::shared_ptr<GpuMemoryManager> memoryManagerShared[MAX_DEVICES] = {nullptr};
thread_local std::shared_ptr<GpuMemoryManager> memoryManagerDevice[MAX_DEVICES] = {nullptr};

#define pitch_alignment 32

DeviceMemory::DeviceMemory()
: data_(nullptr),
  sizeBytes_(0),
  sizeBytesTemp_(0),
  type_(SHARED_MEMORY),
  //  refcount_(nullptr), dev_(new Device())
  refcount_(nullptr),
  event_(nullptr),
  dev_(std::make_shared<Device>())
{
}

DeviceMemory::DeviceMemory(std::shared_ptr<Device> dev)
: data_(nullptr),
  sizeBytes_(0),
  sizeBytesTemp_(0),
  type_(SHARED_MEMORY),
  //  refcount_(nullptr), dev_(new Device())
  refcount_(nullptr),
  event_(nullptr),
  dev_(dev)
{
}

DeviceMemory::DeviceMemory(void * ptr_arg, std::size_t sizeBytes_arg)
: data_(ptr_arg),
  sizeBytes_(sizeBytes_arg),
  sizeBytesTemp_(0),
  type_(SHARED_MEMORY),
  refcount_(nullptr),
  event_(nullptr),
  dev_(std::make_shared<Device>())
{
}

DeviceMemory::DeviceMemory(std::size_t sizeBytes_arg)
: data_(nullptr),
  sizeBytes_(0),
  sizeBytesTemp_(0),
  type_(SHARED_MEMORY),
  refcount_(nullptr),
  event_(nullptr),
  dev_(std::make_shared<Device>())
{
  create(sizeBytes_arg);
}

DeviceMemory::DeviceMemory(std::size_t sizeBytes_arg, std::shared_ptr<Device> dev)
: data_(nullptr),
  sizeBytes_(0),
  sizeBytesTemp_(0),
  type_(SHARED_MEMORY),
  refcount_(nullptr),
  event_(nullptr),
  dev_(dev)
{
  create(sizeBytes_arg);
}

DeviceMemory::DeviceMemory(std::size_t sizeBytes_arg, DeviceType type)
: data_(nullptr),
  sizeBytes_(0),
  sizeBytesTemp_(0),
  type_(SHARED_MEMORY),
  refcount_(nullptr),
  event_(nullptr),
  dev_(std::make_shared<Device>(type))
{
  create(sizeBytes_arg);
}

DeviceMemory::DeviceMemory(std::size_t sizeBtes_arg, MemoryType type)
: data_(nullptr),
  sizeBytes_(0),
  sizeBytesTemp_(0),
  type_(type),
  refcount_(nullptr),
  event_(nullptr),
  dev_(std::make_shared<Device>())
{
  create(sizeBtes_arg, type);
}

DeviceMemory::~DeviceMemory() { release(); }

DeviceMemory::DeviceMemory(const DeviceMemory & other_arg)
: data_(other_arg.data_),
  sizeBytes_(other_arg.sizeBytes_),
  type_(other_arg.type_),
  refcount_(other_arg.refcount_),
  event_(nullptr),
  dev_(other_arg.dev_)
{
  if (refcount_) refcount_->fetch_add(1);
}

DeviceMemory & DeviceMemory::operator=(const DeviceMemory & other_arg)
{
  if (this != &other_arg) {
    if (other_arg.refcount_) other_arg.refcount_->fetch_add(1);
    release();

    data_ = other_arg.data_;
    sizeBytes_ = other_arg.sizeBytes_;
    type_ = other_arg.type_;
    refcount_ = other_arg.refcount_;
    event_ = other_arg.event_;
    dev_ = other_arg.dev_;
  }
  return *this;
}

void DeviceMemory::create_(std::size_t sizeBytes, MemoryType type)
{
  if (dev_ == nullptr) {
    dev_ = std::make_shared<Device>();
  }
  int dev_id = dev_->GetDeviceIndex();

  if (!memoryManagerDevice[dev_id])
    memoryManagerDevice[dev_id] = std::make_shared<GpuMemoryManager>(false);

  if (!memoryManagerShared[dev_id])
    memoryManagerShared[dev_id] = std::make_shared<GpuMemoryManager>(true);

  switch (type) {
    case DEVICE_MEMORY:
      memoryManagerDevice[dev_id]->InitializeQueue(dev_);
      // mtx.lock();
      memoryManagerDevice[dev_id]->GetMemory((void **)&data_, sizeBytes);
      // mtx.unlock();
      refcount_ = new std::atomic<int>(1);
      break;
    case SHARED_MEMORY:
      memoryManagerShared[dev_id]->InitializeQueue(dev_);
      memoryManagerShared[dev_id]->GetMemory((void **)&data_, sizeBytes);
      refcount_ = new std::atomic<int>(1);
      break;
    case HOST_MEMORY:
      data_ = dev_->GetDeviceImpl()->malloc_host(sizeBytes);
      refcount_ = new std::atomic<int>(1);
      break;
    default:
      break;
  }
}

void DeviceMemory::create(std::size_t sizeBytes_arg)
{
  if (sizeBytes_arg == sizeBytes_) return;

  if (data_) release();

  sizeBytes_ = sizeBytes_arg;

  create_(sizeBytes_, type_);
}

void DeviceMemory::create(std::size_t sizeBytes_arg, std::shared_ptr<Device> dev)
{
  if (sizeBytes_arg == sizeBytes_) return;

  if (data_) release();

  dev_ = dev;
  sizeBytes_ = sizeBytes_arg;

  create_(sizeBytes_, type_);
}

void DeviceMemory::create(std::size_t sizeBytes_arg, MemoryType type)
{
  if (sizeBytes_ == sizeBytes_arg) return;

  if (data_) release();

  sizeBytes_ = sizeBytes_arg;
  type_ = type;

  create_(sizeBytes_, type);
}

void DeviceMemory::resize(std::size_t sizeBytes_arg)
{
  if (sizeBytes_arg <= sizeBytes_) {
    sizeBytes_ = sizeBytes_arg;
  } else {
    create(sizeBytes_arg);
  }
}

void DeviceMemory::resize(std::size_t sizeBytes_arg, std::shared_ptr<Device> dev)
{
  dev_ = dev;

  if (sizeBytes_arg <= sizeBytes_) {
    sizeBytes_ = sizeBytes_arg;
  } else {
    create(sizeBytes_arg);
  }
}

void DeviceMemory::copyTo(DeviceMemory & other)
{
  if (empty())
    other.release();
  else {
    other.create(sizeBytes_, type_);
    dev_->GetDeviceImpl()->memcpy(other.data_, data_, sizeBytes_);
  }
}

void DeviceMemory::copyTo(DeviceMemory & other, std::size_t sizeBytes_arg)
{
  if (empty())
    other.release();
  else {
    other.create(sizeBytes_arg, type_);
    dev_->GetDeviceImpl()->memcpy(other.data_, data_, sizeBytes_arg);
  }
}

void DeviceMemory::release()
{
  if (refcount_ && refcount_->fetch_sub(1) == 1) {
    delete refcount_;

    int dev_id = dev_->GetDeviceIndex();

    switch (type_) {
      case DEVICE_MEMORY:
        memoryManagerDevice[dev_id]->ReleaseMemory(data_);
        break;
      case SHARED_MEMORY:
        memoryManagerShared[dev_id]->ReleaseMemory(data_);
        break;
      case HOST_MEMORY:
        dev_->GetDeviceImpl()->free(data_);
        break;
      default:
        break;
    }
  }

  data_ = nullptr;
  sizeBytes_ = 0;
  sizeBytesTemp_ = 0;
  dev_.reset();
  refcount_ = nullptr;
  // event_.reset();
}

void DeviceMemory::updateTempSize(std::size_t size) { sizeBytesTemp_ = size; }

void DeviceMemory::syncEvent()
{
  if (event_) {
    for (auto event : event_->events) event.wait();
  }
}

void DeviceMemory::setEvent(DeviceEvent::Ptr event) { event_ = event; }

void DeviceMemory::clearEvent() { event_->events.clear(); }

DeviceEvent::Ptr DeviceMemory::getEvent() { return event_; }

void DeviceMemory::clear()
{
  if (data_) dev_->GetDeviceImpl()->memset(data_, 0, sizeBytes_);
}

void DeviceMemory::upload(const void * host_ptr_arg, std::size_t sizeBytes_arg)
{
  create(sizeBytes_arg);

  dev_->GetDeviceImpl()->memcpy(data_, host_ptr_arg, sizeBytes_);
}

bool DeviceMemory::upload(
  const void * host_ptr_arg, std::size_t device_begin_byte_offset, std::size_t num_bytes)
{
  if (device_begin_byte_offset + num_bytes > sizeBytes_) {
    return false;
  }
  void * begin = static_cast<char *>(data_) + device_begin_byte_offset;

  dev_->GetDeviceImpl()->memcpy(begin, host_ptr_arg, num_bytes);

  return true;
}

void DeviceMemory::upload_async(const void * host_ptr_arg, std::size_t sizeBytes_arg)
{
  create(sizeBytes_arg);

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  auto sycl_event = dev_->GetDeviceImpl()->memcpy_async(data_, host_ptr_arg, sizeBytes_arg);

  event_->add(sycl_event);
}

bool DeviceMemory::upload_async(
  const void * host_ptr_arg, std::size_t device_begin_byte_offset, std::size_t num_bytes)
{
  if (device_begin_byte_offset + num_bytes > sizeBytes_) {
    return false;
  }

  if (!data_) return false;

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  void * begin = static_cast<char *>(data_) + device_begin_byte_offset;

  auto sycl_event = dev_->GetDeviceImpl()->memcpy_async(begin, host_ptr_arg, num_bytes);

  event_->add(sycl_event);

  return true;
}

void DeviceMemory::download(void * host_ptr_arg)
{
  if (host_ptr_arg && data_) dev_->GetDeviceImpl()->memcpy(host_ptr_arg, data_, sizeBytes_);
}

bool DeviceMemory::download(void * host_ptr_arg, std::size_t num_bytes)
{
  if (host_ptr_arg && data_) dev_->GetDeviceImpl()->memcpy(host_ptr_arg, data_, num_bytes);

  return true;
}

bool DeviceMemory::download_async(void * host_ptr_arg, std::size_t num_bytes)
{
  if ((host_ptr_arg == nullptr) || (data_ == nullptr)) return false;

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  auto sycl_event = dev_->GetDeviceImpl()->memcpy_async(host_ptr_arg, data_, num_bytes);

  event_->add(sycl_event);

  return true;
}

void DeviceMemory::swap(DeviceMemory * other_arg)
{
  std::swap(data_, other_arg->data_);
  std::swap(sizeBytes_, other_arg->sizeBytes_);
  std::swap(sizeBytesTemp_, other_arg->sizeBytesTemp_);
  std::swap(refcount_, other_arg->refcount_);
}

bool DeviceMemory::empty() const { return !data_; }

std::size_t DeviceMemory::sizeBytes() const
{
  if (sizeBytesTemp_ != 0)
    return sizeBytesTemp_;
  else
    return sizeBytes_;
}

void DeviceMemory::fill(float pattern)
{
  if (data_) dev_->GetDeviceImpl()->fill(data_, pattern, sizeBytes_);
}

void DeviceMemory::fill(int pattern)
{
  if (data_) dev_->GetDeviceImpl()->fill(data_, pattern, sizeBytes_);
}

void DeviceMemory::fill(double pattern)
{
  if (data_) dev_->GetDeviceImpl()->fill(data_, pattern, sizeBytes_);
}
void DeviceMemory::fill(uint8_t pattern)
{
  if (data_) dev_->GetDeviceImpl()->fill(data_, pattern, sizeBytes_);
}

void DeviceMemory::fill_async(float pattern)
{
  if (data_ == nullptr) return;

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  sycl::event event = dev_->GetDeviceImpl()->fill_async(data_, pattern, sizeBytes_);
  event_->add(event);
}

void DeviceMemory::fill_async(int pattern)
{
  if (data_ == nullptr) return;

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  sycl::event event = dev_->GetDeviceImpl()->fill_async(data_, pattern, sizeBytes_);
  event_->add(event);
}

void DeviceMemory::fill_async(double pattern)
{
  if (data_ == nullptr) return;

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  sycl::event event = dev_->GetDeviceImpl()->fill_async(data_, pattern, sizeBytes_);
  event_->add(event);
}
void DeviceMemory::fill_async(uint8_t pattern)
{
  if (data_ == nullptr) return;

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  sycl::event event = dev_->GetDeviceImpl()->fill_async(data_, pattern, sizeBytes_);
  event_->add(event);
}
////////////////////////    DeviceMemory2D    /////////////////////////////

DeviceMemory2D::DeviceMemory2D()
: data_(nullptr),
  step_(0),
  minor_(0),
  majorBytes_(0),
  usedMinor_(0),
  usedMajorBytes_(0),
  elem_size_(0),
  type_(SHARED_MEMORY),
  order_(ROW_MAJOR),
  refcount_(nullptr),
  event_(nullptr),
  typeInfo_(nullptr),
  dev_(std::make_shared<Device>())
{
}

/*
DeviceMemory2D::DeviceMemory2D(int minor_arg, int majorBytes_arg, StorageOrder
order) : data_(nullptr), step_(0), minor_(0), majorBytes_(0),
type_(SHARED_MEMORY), usedMinor_(0), usedMajorBytes_(0), order_(order),
  refcount_(nullptr), event_(nullptr), dev_(&std::make_shared<Device>())
{
  create(minor_arg, majorBytes_arg);
}
*/

/*
DeviceMemory2D::DeviceMemory2D(uint32_t cols, uint32_t rows, uint32_t elem_size,
StorageOrder order) : data_(nullptr), step_(0), minor_(0), majorBytes_(0),
type_(SHARED_MEMORY), usedMinor_(0), usedMajorBytes_(0),  elem_size_(elem_size),
order_(order), refcount_(nullptr), event_(nullptr),
dev_(&std::make_shared<Device>())
{
  create(cols, rows);
}
*/

DeviceMemory2D::DeviceMemory2D(
  uint32_t cols, uint32_t rows, const std::type_info * info, StorageOrder order)
: data_(nullptr),
  step_(0),
  minor_(0),
  majorBytes_(0),
  usedMinor_(0),
  usedMajorBytes_(0),
  type_(SHARED_MEMORY),
  order_(order),
  refcount_(nullptr),
  event_(nullptr),
  dev_(std::make_shared<Device>())
{
  typeInfo_ = info;

  if (*typeInfo_ == typeid(float)) {
    elem_size_ = sizeof(float);
  } else if (*typeInfo_ == typeid(int)) {
    elem_size_ = sizeof(int);
  } else if (*typeInfo_ == typeid(char)) {
    elem_size_ = sizeof(char);
  } else if (*typeInfo_ == typeid(unsigned char)) {
    elem_size_ = sizeof(unsigned char);
  } else if (*typeInfo_ == typeid(unsigned short)) {
    elem_size_ = sizeof(unsigned short);
  } else if (*typeInfo_ == typeid(short)) {
    elem_size_ = sizeof(short);
  } else if (*typeInfo_ == typeid(bool)) {
    elem_size_ = sizeof(bool);
  } else if (*typeInfo_ == typeid(double)) {
    elem_size_ = sizeof(double);
  } else {
    throw std::invalid_argument("create doesn't support this type");
  }

  create(cols, rows);
}

DeviceMemory2D::DeviceMemory2D(
  uint32_t cols, uint32_t rows, const std::type_info * info, StorageOrder order,
  std::shared_ptr<Device> dev)
: data_(nullptr),
  step_(0),
  minor_(0),
  majorBytes_(0),
  usedMinor_(0),
  usedMajorBytes_(0),
  type_(SHARED_MEMORY),
  order_(order),
  refcount_(nullptr),
  event_(nullptr),
  dev_(dev)
{
  typeInfo_ = info;

  if (*typeInfo_ == typeid(float)) {
    elem_size_ = sizeof(float);
  } else if (*typeInfo_ == typeid(int)) {
    elem_size_ = sizeof(int);
  } else if (*typeInfo_ == typeid(char)) {
    elem_size_ = sizeof(char);
  } else if (*typeInfo_ == typeid(unsigned char)) {
    elem_size_ = sizeof(unsigned char);
  } else if (*typeInfo_ == typeid(unsigned short)) {
    elem_size_ = sizeof(unsigned short);
  } else if (*typeInfo_ == typeid(short)) {
    elem_size_ = sizeof(short);
  } else if (*typeInfo_ == typeid(bool)) {
    elem_size_ = sizeof(bool);
  } else if (*typeInfo_ == typeid(double)) {
    elem_size_ = sizeof(double);
  } else {
    throw std::invalid_argument("create doesn't support this type");
  }

  create(cols, rows);
}

/*
DeviceMemory2D::DeviceMemory2D(int majorBytes_arg, int minor_arg, Device &dev)
: data_(nullptr), step_(0), minor_(0), majorBytes_(0), type_(SHARED_MEMORY),
  usedMinor_(0), usedMajorBytes_(0), order_(COLUMN_MAJOR),
  refcount_(nullptr),  event_(nullptr), dev_(&dev)
{
  create(minor_arg, majorBytes_arg);
}
*/

DeviceMemory2D::DeviceMemory2D(
  int minor_arg, int majorBytes_arg, void * data_arg, std::size_t step_arg)
: data_(data_arg),
  step_(step_arg),
  minor_(minor_arg),
  majorBytes_(majorBytes_arg),
  usedMinor_(0),
  usedMajorBytes_(0),
  type_(SHARED_MEMORY),
  order_(ROW_MAJOR),
  rect_({0, 0, 0, 0}),
  refcount_(nullptr),
  event_(nullptr),
  dev_(std::make_shared<Device>())
{
}

DeviceMemory2D::~DeviceMemory2D() { release(); }

DeviceMemory2D::DeviceMemory2D(const DeviceMemory2D & other_arg)
: data_(other_arg.data_),
  step_(other_arg.step_),
  minor_(other_arg.minor_),
  majorBytes_(other_arg.majorBytes_),
  usedMinor_(0),
  usedMajorBytes_(0),
  type_(other_arg.type_),
  order_(other_arg.order_),
  rect_(other_arg.rect_),
  refcount_(other_arg.refcount_),
  event_(other_arg.event_),
  dev_(other_arg.dev_),
  elem_size_(other_arg.elem_size_)

{
  if (refcount_) refcount_->fetch_add(1);
}

DeviceMemory2D & DeviceMemory2D::operator=(const DeviceMemory2D & other_arg)
{
  if (this != &other_arg) {
    // if (other_arg.refcount_)
    //   other_arg.refcount_->fetch_add(1);
    release();

    minor_ = other_arg.minor_;
    majorBytes_ = other_arg.majorBytes_;
    usedMinor_ = other_arg.usedMinor_;
    usedMajorBytes_ = other_arg.usedMajorBytes_;
    data_ = other_arg.data_;
    step_ = other_arg.step_;
    event_ = other_arg.event_;
    order_ = other_arg.order_;
    rect_ = other_arg.rect_;
    elem_size_ = other_arg.elem_size_;
    dev_ = other_arg.dev_;

    refcount_ = other_arg.refcount_;
  }
  return *this;
}

#define STEP_DEFAULT_ALIGN(x) (((x) + 31) & ~(0x1f))
void DeviceMemory2D::create_(uint32_t step, uint32_t minor, uint32_t major, MemoryType type)
{
  auto size = minor * step;

  int dev_id = dev_->GetDeviceIndex();

  if (!memoryManagerDevice[dev_id])
    memoryManagerDevice[dev_id] = std::make_shared<GpuMemoryManager>(false);

  if (!memoryManagerShared[dev_id])
    memoryManagerShared[dev_id] = std::make_shared<GpuMemoryManager>(true);

  switch (type) {
    case DEVICE_MEMORY:
      memoryManagerDevice[dev_id]->InitializeQueue(dev_);
      memoryManagerDevice[dev_id]->GetMemory((void **)&data_, size);
      refcount_ = new std::atomic<int>(1);
      break;
    case SHARED_MEMORY:
      memoryManagerShared[dev_id]->InitializeQueue(dev_);
      memoryManagerShared[dev_id]->GetMemory((void **)&data_, size);
      refcount_ = new std::atomic<int>(1);
      break;
    case HOST_MEMORY:
      data_ = dev_->GetDeviceImpl()->malloc_host(size);
      refcount_ = new std::atomic<int>(1);
      break;
    default:
      break;
  }
}

void DeviceMemory2D::updateTempSize(int minor_arg, int majorBytes_arg)
{
  usedMajorBytes_ = majorBytes_arg;
  usedMinor_ = minor_arg;
}

void DeviceMemory2D::create(uint32_t cols, uint32_t rows)
{
  auto minor_arg = (order_ == COLUMN_MAJOR) ? cols : rows;
  auto major_arg = (order_ == COLUMN_MAJOR) ? rows : cols;

  if (minor_ == minor_arg && majorBytes_ == major_arg) return;

  minor_ = minor_arg;
  majorBytes_ = major_arg;

  if (major_arg > 0 && minor_arg > 0) {
    if (data_) release();

    step_ = align(majorBytes_ * elem_size_, pitch_alignment);

    create_(step_, minor_, majorBytes_, type_);

    rect_ = {0, 0, cols, rows};
  }
}

void DeviceMemory2D::create(uint32_t cols, uint32_t rows, uint32_t step_arg)
{
  auto minor_arg = (order_ == COLUMN_MAJOR) ? cols : rows;
  auto major_arg = (order_ == COLUMN_MAJOR) ? rows : cols;

  if (minor_ == minor_arg && majorBytes_ == major_arg) return;

  minor_ = minor_arg;
  majorBytes_ = major_arg;

  if (major_arg > 0 && minor_arg > 0) {
    if (data_) release();

    step_ = step_arg;

    create_(step_, minor_, majorBytes_, type_);

    rect_ = {0, 0, cols, rows};
  }
}

/*
void
DeviceMemory2D::create(int minor_arg, int majorBytes_arg, MemoryType type)
{
  if (minor_ == minor_arg && majorBytes_ == majorBytes_arg)
    return;

  if (majorBytes_arg > 0 && minor_arg > 0) {
    if (data_)
      release();

    minor_ = minor_arg;
    majorBytes_ = majorBytes_arg;

    create_(step_, minor_, majorBytes_, type);
  }
}
*/

void DeviceMemory2D::resize(uint32_t cols, uint32_t rows)
{
  auto minor_arg = (order_ == COLUMN_MAJOR) ? cols : rows;
  auto major_arg = (order_ == COLUMN_MAJOR) ? rows : cols;

  if ((minor_arg < minor_) || (major_arg < majorBytes_)) release();

  create(cols, rows);

  rect_ = {0, 0, cols, rows};
  // minor_ = minor_arg;
  // majorBytes_ = major_arg;
}

void DeviceMemory2D::resize(uint32_t cols, uint32_t rows, std::shared_ptr<Device> dev)
{
  auto minor_arg = (order_ == COLUMN_MAJOR) ? cols : rows;
  auto major_arg = (order_ == COLUMN_MAJOR) ? rows : cols;

  if ((minor_arg < minor_) || (major_arg < majorBytes_)) release();

  create(cols, rows);

  rect_ = {0, 0, cols, rows};

  // minor_ = minor_arg;
  // majorBytes_ = major_arg;
}

template <typename U>
DeviceEvent::Ptr DeviceMemory2D::fill_(U pattern)
{
  auto eventPtr = DeviceEvent::create();

  auto copy_size = minor_ * majorBytes_;

  sycl::event event = dev_->GetDeviceImpl()->fill_async(data_, pattern, copy_size);

  eventPtr->add(event);

  return eventPtr;
}

void DeviceMemory2D::fill(void * pattern)
{
  DeviceEvent::Ptr event;

  if (data_ == nullptr) throw std::runtime_error("memory has not allocated");

  if (*typeInfo_ == typeid(float)) {
    float pattern_value;
    std::memcpy(&pattern_value, &pattern, sizeof(float));
    event = fill_(pattern_value);
  } else if (*typeInfo_ == typeid(int)) {
    int pattern_value;
    std::memcpy(&pattern_value, &pattern, sizeof(int));
    event = fill_(pattern_value);
  } else if (*typeInfo_ == typeid(char)) {
    char pattern_value;
    std::memcpy(&pattern_value, &pattern, sizeof(char));
    event = fill_(pattern_value);
  } else if (*typeInfo_ == typeid(unsigned char)) {
    unsigned char pattern_value;
    std::memcpy(&pattern_value, &pattern, sizeof(unsigned char));
    event = fill_(pattern_value);
  } else if (*typeInfo_ == typeid(unsigned short)) {
    unsigned short pattern_value;
    std::memcpy(&pattern_value, &pattern, sizeof(unsigned short));
    event = fill_(pattern_value);
  } else if (*typeInfo_ == typeid(short)) {
    short pattern_value;
    std::memcpy(&pattern_value, &pattern, sizeof(short));
    event = fill_(pattern_value);
  } else if (*typeInfo_ == typeid(bool)) {
    bool pattern_value;
    std::memcpy(&pattern_value, &pattern, sizeof(bool));
    event = fill_(pattern_value);
  } else if (*typeInfo_ == typeid(double)) {
    double pattern_value;
    std::memcpy(&pattern_value, &pattern, sizeof(double));
    event = fill_(pattern_value);
  } else {
    throw std::invalid_argument("copyTo doesn't support this type");
  }

  setEvent(event);
}

void DeviceMemory2D::release()
{
  if (refcount_ && refcount_->fetch_sub(1) == 1) {
    delete refcount_;

    int dev_id = dev_->GetDeviceIndex();

    switch (type_) {
      case DEVICE_MEMORY:
        memoryManagerDevice[dev_id]->ReleaseMemory(data_);
        break;
      case SHARED_MEMORY:
        memoryManagerShared[dev_id]->ReleaseMemory(data_);
        break;
      case HOST_MEMORY:
        dev_->GetDeviceImpl()->free(data_);
        break;
      default:
        break;
    }
  }

  minor_ = 0;
  majorBytes_ = 0;
  usedMajorBytes_ = 0;
  usedMinor_ = 0;
  step_ = 0;
  dev_.reset();
  // event_.reset();
  data_ = nullptr;
  refcount_ = nullptr;
}
void DeviceMemory2D::copyTo(DeviceMemory2D & other)
{
  if (empty())
    other.release();
  else {
    other.create(minor_, majorBytes_);

    sycl::queue * q = dev_->GetDeviceImpl()->get_queue();

    dpct::detail::dpct_memcpy(
      *q, other.data_, data_, other.step_, step_, minor_, majorBytes_, dpct::device_to_device);

    dev_->GetDeviceImpl()->wait();
  }
}

template <typename U>
DeviceEvent::Ptr DeviceMemory2D::copyTo_(
  U * src, U * dst, char * mask, DeviceEvent * maskEvent) const
{
  sycl::queue * q = dev_->GetDeviceImpl()->get_queue();

  size_t blkSize = 128 / elem_size_;
  size_t majorBlk = (majorBytes_ + blkSize - 1) / blkSize;

  sycl::range global{majorBlk * blkSize, minor_};
  sycl::range local{blkSize, 1};

  sycl::event event = q->submit([&](sycl::handler & cgh) {
    auto src_event = event_;
    if (src_event) cgh.depends_on(src_event->events);

    if (maskEvent) cgh.depends_on(maskEvent->events);

    auto src_ptr = src;
    auto dest_ptr = dst;
    auto mask_ptr = mask;
    auto majorBytes = majorBytes_;
    auto minor = minor_;

    cgh.parallel_for(
      sycl::nd_range<2>(global, local), [=](sycl::nd_item<2> it) [[sycl::reqd_sub_group_size(32)]] {
        auto g_x = it.get_global_id(0);
        auto g_y = it.get_global_id(1);

        if ((g_x > majorBytes) || (g_y > minor)) return;

        int idx = g_y * majorBytes + g_x;

        if (mask_ptr[idx]) {
          dest_ptr[idx] = src_ptr[idx];
        }
      });
  });

  auto eventPtr = DeviceEvent::create();
  eventPtr->add(event);
  return eventPtr;
}

void DeviceMemory2D::copyTo(DeviceMemory2D & dest, const DeviceMemory2D & mask) const
{
  // Check current minor, majorbytes are match with both other, and mask
  if (
    (minor_ != dest.minor()) || (minor_ != mask.minor()) || (majorBytes_ != dest.majorBytes()) ||
    (majorBytes_ != mask.majorBytes())) {
    throw std::invalid_argument("copyTo matrix must have same width and height");
  }

  if ((data_ == nullptr) || (dest.data_ == nullptr))
    throw std::runtime_error("memory has not allocated");

  DeviceEvent::Ptr event;

  if (*typeInfo_ == typeid(float)) {
    event = copyTo_((float *)data_, (float *)dest.data_, (char *)mask.data_, mask.event_.get());
  } else if (*typeInfo_ == typeid(int)) {
    event = copyTo_((int *)data_, (int *)dest.data_, (char *)mask.data_, mask.event_.get());
  } else if (*typeInfo_ == typeid(char)) {
    event = copyTo_((char *)data_, (char *)dest.data_, (char *)mask.data_, mask.event_.get());
  } else if (*typeInfo_ == typeid(unsigned char)) {
    event = copyTo_(
      (unsigned char *)data_, (unsigned char *)dest.data_, (char *)mask.data_, mask.event_.get());
  } else if (*typeInfo_ == typeid(unsigned short)) {
    event = copyTo_(
      (unsigned short *)data_, (unsigned short *)dest.data_, (char *)mask.data_, mask.event_.get());
  } else if (*typeInfo_ == typeid(short)) {
    event = copyTo_((short *)data_, (short *)dest.data_, (char *)mask.data_, mask.event_.get());
  } else if (*typeInfo_ == typeid(bool)) {
    event = copyTo_((bool *)data_, (bool *)dest.data_, (char *)mask.data_, mask.event_.get());
  } else if (*typeInfo_ == typeid(double)) {
    event = copyTo_((double *)data_, (double *)dest.data_, (char *)mask.data_, mask.event_.get());
  } else {
    throw std::invalid_argument("copyTo doesn't support this type");
  }

  dest.setEvent(event);
}

void DeviceMemory2D::upload(
  const void * host_ptr_arg, uint32_t host_step_arg, uint32_t cols, uint32_t rows)
{
  auto minor_arg = (order_ == COLUMN_MAJOR) ? cols : rows;

  create(cols, rows, host_step_arg);

  auto copy_size = host_step_arg * elem_size_ * minor_arg;

  dev_->GetDeviceImpl()->memcpy(data_, host_ptr_arg, copy_size);
}

void DeviceMemory2D::upload(const void * host_ptr_arg)
{
  if ((data_ == nullptr) || (host_ptr_arg == nullptr))
    throw std::runtime_error("memory has not allocated");

  if (step_ == majorBytes_) {
    auto copy_size = majorBytes_ * elem_size_ * minor_;

    dev_->GetDeviceImpl()->memcpy(data_, host_ptr_arg, copy_size);
  } else {
    dev_->GetDeviceImpl()->memcpy(data_, host_ptr_arg, majorBytes_, minor_, majorBytes_, step_);
  }
}

void DeviceMemory2D::upload_async(
  const void * host_ptr_arg, uint32_t host_step_arg, uint32_t cols, uint32_t rows)
{
  auto minor_arg = (order_ == COLUMN_MAJOR) ? cols : rows;
  auto major_arg = (order_ == COLUMN_MAJOR) ? rows : cols;

  create(minor_arg, major_arg, host_step_arg);

  auto copy_size = host_step_arg * elem_size_ * minor_arg;

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  sycl::event event = dev_->GetDeviceImpl()->memcpy_async(data_, host_ptr_arg, copy_size);

  event_->add(event);
}

void DeviceMemory2D::upload_async(const void * host_ptr_arg)
{
  if ((data_ == nullptr) || (host_ptr_arg == nullptr))
    throw std::runtime_error("memory has not allocated");

  auto copy_size = majorBytes_ * elem_size_ * minor_;

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  sycl::event event = dev_->GetDeviceImpl()->memcpy_async(data_, host_ptr_arg, copy_size);

  event_->add(event);
}

void DeviceMemory2D::download(
  void * host_ptr_arg, uint32_t host_step_arg, uint32_t cols, uint32_t rows)
{
  if ((data_ == nullptr) || (host_ptr_arg == nullptr))
    throw std::runtime_error("memory has not allocated");

  auto minor_arg = (order_ == COLUMN_MAJOR) ? cols : rows;

  if (step_ == majorBytes_) {
    auto copy_size = host_step_arg * elem_size_ * minor_arg;

    dev_->GetDeviceImpl()->memcpy(host_ptr_arg, data_, copy_size);
  } else {
    syncEvent();
    dev_->GetDeviceImpl()->memcpy(
      host_ptr_arg, data_, majorBytes_, minor_arg, step_, host_step_arg);
  }
}
void DeviceMemory2D::swap(DeviceMemory2D * other_arg)
{
  std::swap(data_, other_arg->data_);
  std::swap(step_, other_arg->step_);
  std::swap(elem_size_, other_arg->elem_size_);
  std::swap(order_, other_arg->order_);
  std::swap(type_, other_arg->type_);
  std::swap(minor_, other_arg->minor_);
  std::swap(majorBytes_, other_arg->majorBytes_);
  std::swap(usedMinor_, other_arg->usedMinor_);
  std::swap(usedMajorBytes_, other_arg->usedMajorBytes_);
  std::swap(refcount_, other_arg->refcount_);
}

bool DeviceMemory2D::empty() const { return !data_; }

int DeviceMemory2D::majorBytes() const
{
  if (usedMajorBytes_)
    return usedMajorBytes_;
  else
    return majorBytes_;
}

int DeviceMemory2D::minor() const
{
  if (usedMinor_)
    return usedMinor_;
  else
    return minor_;
}

std::size_t DeviceMemory2D::step() const { return step_; }

void DeviceMemory2D::setEvent(DeviceEvent::Ptr event) { event_ = event; }

void DeviceMemory2D::clearEvent()
{
  if (event_) {
    event_->events.clear();
    event_.reset();
  }
}

DeviceEvent::Ptr DeviceMemory2D::getEvent() { return event_; }

void DeviceMemory2D::syncEvent()
{
  if (event_) {
    for (auto event : event_->events) event.wait();
  }
}

template <typename U>
DeviceEvent::Ptr DeviceMemory2D::mul_(U * dst, U * other, DeviceEvent * otherEvent)
{
  sycl::queue * q = dev_->GetDeviceImpl()->get_queue();

  size_t blkSize = 128;
  size_t majorBlk = (majorBytes_ + blkSize - 1) / blkSize;

  sycl::range global{majorBlk * blkSize, minor_};
  sycl::range local{blkSize, 1};

  sycl::event event = q->submit([&](sycl::handler & cgh) {
    if (otherEvent) cgh.depends_on(otherEvent->events);

    auto other_ptr = other;
    auto dest_ptr = dst;
    auto majorBytes = majorBytes_;
    auto minor = minor_;

    cgh.parallel_for(
      sycl::nd_range<2>(global, local), [=](sycl::nd_item<2> it) [[sycl::reqd_sub_group_size(16)]] {
        auto g_x = it.get_global_id(0);
        auto g_y = it.get_global_id(1);

        if ((g_x > majorBytes) || (g_y > minor)) return;

        int idx = g_y * majorBytes + g_x;

        dest_ptr[idx] *= other_ptr[idx];
      });
  });

  auto eventPtr = DeviceEvent::create();
  eventPtr->add(event);
  return eventPtr;
}

void DeviceMemory2D::mul(DeviceMemory2D * other)
{
  // Check current minor, majorbytes are match with both other, and mask
  if ((minor_ != other->minor()) || (majorBytes_ != other->majorBytes())) {
    throw std::invalid_argument("multiply matrix must have same width and height");
  }

  if ((data_ == nullptr) || (other->data_ == nullptr))
    throw std::runtime_error("memory has not allocated");

  DeviceEvent::Ptr event;

  if (*typeInfo_ == typeid(float)) {
    event = mul_((float *)data_, (float *)other->data_, other->event_.get());
  } else if (*typeInfo_ == typeid(int)) {
    event = mul_((int *)data_, (int *)other->data_, other->event_.get());
  } else if (*typeInfo_ == typeid(char)) {
    event = mul_((char *)data_, (char *)other->data_, other->event_.get());
  } else if (*typeInfo_ == typeid(unsigned char)) {
    event = mul_((unsigned char *)data_, (unsigned char *)other->data_, other->event_.get());
  } else if (*typeInfo_ == typeid(unsigned short)) {
    event = mul_((unsigned short *)data_, (unsigned short *)other->data_, other->event_.get());
  } else if (*typeInfo_ == typeid(short)) {
    event = mul_((short *)data_, (short *)other->data_, other->event_.get());
  } else if (*typeInfo_ == typeid(bool)) {
    event = mul_((bool *)data_, (bool *)other->data_, other->event_.get());
  } else if (*typeInfo_ == typeid(double)) {
    event = mul_((double *)data_, (double *)other->data_, other->event_.get());
  } else {
    throw std::invalid_argument("mul doesn't support this type");
  }

  setEvent(event);
}

#endif /* __DEVICE_MEMORY_IMPL__ */
