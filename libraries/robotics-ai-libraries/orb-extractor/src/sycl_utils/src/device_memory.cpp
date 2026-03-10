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

#include <cstdlib>
#include <mutex>
#include <sstream>
#include <thread>

#include "device_impl.h"
#include "dpct/dpct.hpp"
#include "gpu_memory_manager.h"

// Debug instrumentation for GPU memory tracking
// Enable by setting environment variable: export GPU_MEM_DEBUG=1
static bool gpu_mem_debug_enabled()
{
  static int enabled = -1;
  if (enabled < 0) {
    const char * env = std::getenv("GPU_MEM_DEBUG");
    enabled = (env && (std::string(env) == "1" || std::string(env) == "true")) ? 1 : 0;
  }
  return enabled == 1;
}

static std::mutex g_debug_mutex;
static std::mutex g_free_mutex;  // Protect free operations from race conditions

static std::string get_thread_id_str()
{
  std::ostringstream oss;
  oss << std::this_thread::get_id();
  return oss.str();
}

#define GPU_MEM_DEBUG(fmt, ...)                                                                  \
  do {                                                                                           \
    if (gpu_mem_debug_enabled()) {                                                               \
      std::lock_guard<std::mutex> lock(g_debug_mutex);                                           \
      fprintf(stderr, "[GPU_MEM tid=%s] " fmt "\n", get_thread_id_str().c_str(), ##__VA_ARGS__); \
      fflush(stderr);                                                                            \
    }                                                                                            \
  } while (0)

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

// Check if memory pooling is disabled (safer but slower)
static bool use_direct_alloc()
{
  static int enabled = -1;
  if (enabled < 0) {
    const char * env = std::getenv("GPU_NO_POOL");
    enabled = (env && (std::string(env) == "1" || std::string(env) == "true")) ? 1 : 0;
    if (enabled) {
      fprintf(stderr, "[GPU_MEM] Memory pooling DISABLED (GPU_NO_POOL=1)\n");
    }
  }
  return enabled == 1;
}

void DeviceMemory::create_(std::size_t sizeBytes, MemoryType type)
{
  GPU_MEM_DEBUG(
    "create_ START: this=%p, sizeBytes=%zu, type=%d", (void *)this, sizeBytes, (int)type);

  if (dev_ == nullptr) {
    GPU_MEM_DEBUG("create_: dev_ was null, creating new Device");
    dev_ = std::make_shared<Device>();
  }
  int dev_id = dev_->GetDeviceIndex();
  GPU_MEM_DEBUG("create_: dev_id=%d", dev_id);

  // Direct allocation mode (bypasses memory pool for stability)
  if (use_direct_alloc() || dev_id < 0 || dev_id >= MAX_DEVICES) {
    GPU_MEM_DEBUG("create_: using direct allocation (no pool)");
    switch (type) {
      case DEVICE_MEMORY:
        data_ = dev_->GetDeviceImpl()->malloc_device(sizeBytes);
        break;
      case SHARED_MEMORY:
        data_ = dev_->GetDeviceImpl()->malloc_shared(sizeBytes);
        break;
      case HOST_MEMORY:
        data_ = dev_->GetDeviceImpl()->malloc_host(sizeBytes);
        break;
      default:
        break;
    }
    refcount_ = new std::atomic<int>(1);
    type_ = type;  // Make sure type is set for release()
    GPU_MEM_DEBUG("create_ (direct) END: this=%p, data_=%p", (void *)this, data_);
    return;
  }

  if (!memoryManagerDevice[dev_id]) {
    GPU_MEM_DEBUG("create_: creating new GpuMemoryManager(device) for dev_id=%d", dev_id);
    memoryManagerDevice[dev_id] = std::make_shared<GpuMemoryManager>(false);
  }

  if (!memoryManagerShared[dev_id]) {
    GPU_MEM_DEBUG("create_: creating new GpuMemoryManager(shared) for dev_id=%d", dev_id);
    memoryManagerShared[dev_id] = std::make_shared<GpuMemoryManager>(true);
  }

  switch (type) {
    case DEVICE_MEMORY:
      GPU_MEM_DEBUG("create_: DEVICE_MEMORY allocation, sizeBytes=%zu", sizeBytes);
      memoryManagerDevice[dev_id]->InitializeQueue(dev_);
      memoryManagerDevice[dev_id]->GetMemory((void **)&data_, sizeBytes);
      refcount_ = new std::atomic<int>(1);
      GPU_MEM_DEBUG(
        "create_: DEVICE_MEMORY allocated data_=%p, refcount_=%p", data_, (void *)refcount_);
      break;
    case SHARED_MEMORY:
      GPU_MEM_DEBUG("create_: SHARED_MEMORY allocation, sizeBytes=%zu", sizeBytes);
      memoryManagerShared[dev_id]->InitializeQueue(dev_);
      memoryManagerShared[dev_id]->GetMemory((void **)&data_, sizeBytes);
      refcount_ = new std::atomic<int>(1);
      GPU_MEM_DEBUG(
        "create_: SHARED_MEMORY allocated data_=%p, refcount_=%p", data_, (void *)refcount_);
      break;
    case HOST_MEMORY:
      GPU_MEM_DEBUG("create_: HOST_MEMORY allocation, sizeBytes=%zu", sizeBytes);
      data_ = dev_->GetDeviceImpl()->malloc_host(sizeBytes);
      refcount_ = new std::atomic<int>(1);
      GPU_MEM_DEBUG(
        "create_: HOST_MEMORY allocated data_=%p, refcount_=%p", data_, (void *)refcount_);
      break;
    default:
      GPU_MEM_DEBUG("create_: UNKNOWN type=%d", (int)type);
      break;
  }
  GPU_MEM_DEBUG("create_ END: this=%p, data_=%p", (void *)this, data_);
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
  // Pass in dev directly to create function
  //dev_ = dev;

  if (sizeBytes_arg <= sizeBytes_) {
    sizeBytes_ = sizeBytes_arg;
  } else {
    create(sizeBytes_arg, dev);
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
  GPU_MEM_DEBUG(
    "release START: this=%p, data_=%p, refcount_=%p, type=%d", (void *)this, data_,
    (void *)refcount_, (int)type_);

  if (refcount_) {
    int prev_count = refcount_->fetch_sub(1);
    GPU_MEM_DEBUG("release: prev refcount was %d", prev_count);

    if (prev_count == 1) {
      GPU_MEM_DEBUG("release: refcount reached 0, freeing memory");
      delete refcount_;
      refcount_ = nullptr;  // Mark as deleted to prevent double-free attempts

      // Skip if data is already null (nothing to free)
      if (!data_) {
        GPU_MEM_DEBUG("release: data_ is already null, nothing to free");
      } else if (!dev_) {
        GPU_MEM_DEBUG("release ERROR: dev_ is null but we need to free data_=%p!", data_);
        // Cannot free - will leak memory but better than crash
      } else if (!dev_->GetDeviceImpl()) {
        GPU_MEM_DEBUG("release ERROR: GetDeviceImpl() is null, cannot free data_=%p!", data_);
        // Cannot free - will leak memory but better than crash
      } else {
        // Lock to prevent race conditions during free
        std::lock_guard<std::mutex> free_lock(g_free_mutex);

        int dev_id = dev_->GetDeviceIndex();
        GPU_MEM_DEBUG("release: dev_id=%d, freeing data_=%p", dev_id, data_);

        // Direct free mode or invalid dev_id - always free directly
        if (use_direct_alloc() || dev_id < 0 || dev_id >= MAX_DEVICES) {
          GPU_MEM_DEBUG("release: direct free mode, freeing directly");
          dev_->GetDeviceImpl()->free(data_);
        } else {
          switch (type_) {
            case DEVICE_MEMORY:
              GPU_MEM_DEBUG(
                "release: DEVICE_MEMORY, memoryManagerDevice[%d]=%p", dev_id,
                (void *)memoryManagerDevice[dev_id].get());
              if (memoryManagerDevice[dev_id]) {
                if (!memoryManagerDevice[dev_id]->ReleaseMemory(data_)) {
                  // Cross-thread release: pointer not in this thread's pool, free directly
                  GPU_MEM_DEBUG("release: cross-thread release DEVICE_MEMORY, freeing directly");
                  dev_->GetDeviceImpl()->free(data_);
                } else {
                  GPU_MEM_DEBUG("release: returned to DEVICE_MEMORY pool");
                }
              } else {
                // No manager on this thread, free directly
                GPU_MEM_DEBUG("release: no manager on thread, freeing DEVICE_MEMORY directly");
                dev_->GetDeviceImpl()->free(data_);
              }
              break;
            case SHARED_MEMORY:
              GPU_MEM_DEBUG(
                "release: SHARED_MEMORY, memoryManagerShared[%d]=%p", dev_id,
                (void *)memoryManagerShared[dev_id].get());
              if (memoryManagerShared[dev_id]) {
                if (!memoryManagerShared[dev_id]->ReleaseMemory(data_)) {
                  // Cross-thread release: pointer not in this thread's pool, free directly
                  GPU_MEM_DEBUG("release: cross-thread release SHARED_MEMORY, freeing directly");
                  dev_->GetDeviceImpl()->free(data_);
                } else {
                  GPU_MEM_DEBUG("release: returned to SHARED_MEMORY pool");
                }
              } else {
                // No manager on this thread, free directly
                GPU_MEM_DEBUG("release: no manager on thread, freeing SHARED_MEMORY directly");
                dev_->GetDeviceImpl()->free(data_);
              }
              break;
            case HOST_MEMORY:
              GPU_MEM_DEBUG("release: HOST_MEMORY, freeing directly");
              dev_->GetDeviceImpl()->free(data_);
              break;
            default:
              GPU_MEM_DEBUG("release: UNKNOWN type=%d", (int)type_);
              break;
          }
        }
      }
    }
  }

  data_ = nullptr;
  sizeBytes_ = 0;
  sizeBytesTemp_ = 0;
  dev_.reset();
  refcount_ = nullptr;
  // event_.reset();
  GPU_MEM_DEBUG("release END: this=%p", (void *)this);
}

void DeviceMemory::updateTempSize(std::size_t size) { sizeBytesTemp_ = size; }

void DeviceMemory::syncEvent()
{
  GPU_MEM_DEBUG(
    "syncEvent START: this=%p, event_=%p, data_=%p, dev_=%p, refcount_=%p", (void *)this,
    (void *)event_.get(), data_, (void *)dev_.get(), (void *)refcount_);
  if (event_) {
    GPU_MEM_DEBUG("syncEvent: event_ has %zu events to wait on", event_->events.size());
    size_t idx = 0;
    for (auto event : event_->events) {
      GPU_MEM_DEBUG("syncEvent: waiting on event[%zu]", idx);
      try {
        event.wait();
        GPU_MEM_DEBUG("syncEvent: event[%zu] completed", idx);
      } catch (const std::exception & e) {
        GPU_MEM_DEBUG("syncEvent ERROR: event[%zu] threw exception: %s", idx, e.what());
        throw;
      }
      idx++;
    }
  } else {
    GPU_MEM_DEBUG("syncEvent: event_ is null, nothing to wait on");
  }
  // Validate state after sync
  GPU_MEM_DEBUG(
    "syncEvent END: this=%p, data_=%p valid=%d, dev_ valid=%d", (void *)this, data_,
    (data_ != nullptr), (dev_ != nullptr));
}

void DeviceMemory::setEvent(DeviceEvent::Ptr event)
{
  GPU_MEM_DEBUG(
    "setEvent: this=%p, old event_=%p, new event=%p", (void *)this, (void *)event_.get(),
    (void *)event.get());
  event_ = event;
}

void DeviceMemory::clearEvent()
{
  GPU_MEM_DEBUG("clearEvent: this=%p, event_=%p", (void *)this, (void *)event_.get());
  if (event_) {
    GPU_MEM_DEBUG("clearEvent: clearing %zu events", event_->events.size());
    event_->events.clear();
  } else {
    GPU_MEM_DEBUG("clearEvent WARNING: event_ is null!");
  }
}

DeviceEvent::Ptr DeviceMemory::getEvent() { return event_; }

void DeviceMemory::clear()
{
  GPU_MEM_DEBUG(
    "clear: this=%p, data_=%p, dev_=%p, sizeBytes_=%zu", (void *)this, data_, (void *)dev_.get(),
    sizeBytes_);
  if (data_) {
    if (!dev_) {
      GPU_MEM_DEBUG("clear ERROR: dev_ is null but data_ is not!");
      return;
    }
    dev_->GetDeviceImpl()->memset(data_, 0, sizeBytes_);
  }
}

void DeviceMemory::upload(const void * host_ptr_arg, std::size_t sizeBytes_arg)
{
  GPU_MEM_DEBUG(
    "upload: this=%p, host_ptr=%p, sizeBytes=%zu", (void *)this, host_ptr_arg, sizeBytes_arg);
  create(sizeBytes_arg);

  dev_->GetDeviceImpl()->memcpy(data_, host_ptr_arg, sizeBytes_);
  GPU_MEM_DEBUG("upload DONE: this=%p, data_=%p", (void *)this, data_);
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
  GPU_MEM_DEBUG(
    "download: this=%p, host_ptr=%p, data_=%p, sizeBytes_=%zu, dev_=%p", (void *)this, host_ptr_arg,
    data_, sizeBytes_, (void *)dev_.get());
  if (host_ptr_arg && data_) {
    if (!dev_) {
      GPU_MEM_DEBUG("download ERROR: dev_ is null!");
      return;
    }
    dev_->GetDeviceImpl()->memcpy(host_ptr_arg, data_, sizeBytes_);
    GPU_MEM_DEBUG("download DONE: this=%p", (void *)this);
  } else {
    GPU_MEM_DEBUG("download SKIPPED: host_ptr=%p, data_=%p", host_ptr_arg, data_);
  }
}

bool DeviceMemory::download(void * host_ptr_arg, std::size_t num_bytes)
{
  GPU_MEM_DEBUG(
    "download(num): this=%p, host_ptr=%p, data_=%p, num_bytes=%zu, dev_=%p", (void *)this,
    host_ptr_arg, data_, num_bytes, (void *)dev_.get());
  if (host_ptr_arg && data_) {
    if (!dev_) {
      GPU_MEM_DEBUG("download(num) ERROR: dev_ is null!");
      return false;
    }
    dev_->GetDeviceImpl()->memcpy(host_ptr_arg, data_, num_bytes);
    GPU_MEM_DEBUG("download(num) DONE: this=%p", (void *)this);
  } else {
    GPU_MEM_DEBUG("download(num) SKIPPED: host_ptr=%p, data_=%p", host_ptr_arg, data_);
  }

  return true;
}

bool DeviceMemory::download_async(void * host_ptr_arg, std::size_t num_bytes)
{
  GPU_MEM_DEBUG(
    "download_async: this=%p, host_ptr=%p, data_=%p, num_bytes=%zu", (void *)this, host_ptr_arg,
    data_, num_bytes);
  if ((host_ptr_arg == nullptr) || (data_ == nullptr)) {
    GPU_MEM_DEBUG("download_async SKIPPED: host_ptr=%p, data_=%p", host_ptr_arg, data_);
    return false;
  }

  if (event_ == nullptr) {
    event_ = DeviceEvent::create();
  }

  auto sycl_event = dev_->GetDeviceImpl()->memcpy_async(host_ptr_arg, data_, num_bytes);

  event_->add(sycl_event);
  GPU_MEM_DEBUG("download_async QUEUED: this=%p", (void *)this);

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
