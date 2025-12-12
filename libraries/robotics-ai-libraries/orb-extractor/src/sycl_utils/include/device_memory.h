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
 *  Author: Anatoly Baskeheev, Itseez Ltd
 *  Author: Chon Ming Lee, Intel
 *
 */
// SPDX-License-Identifier: BSD-3-Clause

#ifndef __DEVICE_MEMORY_H__
#define __DEVICE_MEMORY_H__

#include <atomic>
#include <memory>
#include <utility>

#include "device.h"

// class DeviceEvent;

///////////////////////////////////////////////////////////////////////////////
/** \brief @b DeviceMemory class
 *
 * \note This is a BLOB container class with reference counting for GPU memory.
 *
 * \author Anatoly Baksheev
 */

class SYCL_UTILS_API DeviceMemory
{
public:
  /** \brief Empty constructor. */
  DeviceMemory();

  /** \brief Destructor. */
  ~DeviceMemory();

  DeviceMemory(std::shared_ptr<Device> dev);

  /** \brief Allocates internal buffer in GPU memory
   * \param sizeBytes_arg amount of memory to allocate
   * */
  DeviceMemory(std::size_t sizeBytes_arg);

  template <typename A>
  DeviceMemory(std::size_t sizeBytes_arg, A pattern, bool wait);

  /** \brief Initializes with user allocated buffer. Reference counting is
   * disabled in this case. \param ptr_arg pointer to buffer \param
   * sizeBytes_arg buffer size
   * */
  DeviceMemory(void * ptr_arg, std::size_t sizeBytes_arg);

  DeviceMemory(std::size_t sizeBytes_arg, std::shared_ptr<Device> dev);

  DeviceMemory(std::size_t sizeBytes_arg, DeviceType type);
  /** \brief Initializes with user allocated buffer. Reference counting is
   * disabled in this case. \param sizeBytes_arg buffer size \param type Memory
   * type such as shared, device, or host
   * */
  DeviceMemory(std::size_t sizeBytes_arg, MemoryType type);

  /** \brief Copy constructor. Just increments reference counter. */
  DeviceMemory(const DeviceMemory & other_arg);

  /** \brief Assignment operator. Just increments reference counter. */
  DeviceMemory & operator=(const DeviceMemory & other_arg);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param sizeBytes_arg buffer size
   * */
  void create(std::size_t sizeBytes_arg);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param sizeBytes_arg buffer size \param
   * dev use this device to allocate
   * */
  void create(std::size_t sizeBytes_arg, std::shared_ptr<Device> dev);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param sizeBytes_arg buffer size \param
   * type device memory type (MemoryType)
   * */
  void create(std::size_t sizeBytes_arg, MemoryType type);

  /** \brief Change the size without reallocate the buffer if the new size is
   * smaller. \param sizeBytes_arg buffer size
   * */
  void resize(std::size_t sizeBytes_arg);

  /** \brief Change the size without reallocate the buffer if the new size is
   * smaller. \param sizeBytes_arg buffer size \param dev use this device to
   * allocate
   * */
  void resize(std::size_t sizeBytes_arg, std::shared_ptr<Device> dev);

  /** \brief Decrements reference counter and releases internal buffer if
   * needed. */
  void release();

  /** \brief Fill all data with the pattern.
   * \param pattern
   * Explicit specialize template doesn't work.  Declare multiple common types
   * for fill
   * */
  void fill(float pattern);

  void fill(int pattern);

  void fill(double pattern);

  void fill(uint8_t pattern);

  /** \brief Fill all data with the pattern.
   * \param pattern
   * Explicit specialize template doesn't work.  Declare multiple common types
   * for fill
   * */
  void fill_async(float pattern);

  void fill_async(int pattern);

  void fill_async(double pattern);

  void fill_async(uint8_t pattern);

  /** \brief Performs data copying. If destination size differs it will be
   * reallocated. \param other destination container
   * */
  void copyTo(DeviceMemory & other);

  /** \brief Performs data copying. Copy based on requested size
   * \param other destination container
   * \param sizeBytes_arg buffer size
   * */
  void copyTo(DeviceMemory & other, std::size_t sizeBytes_arg);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that intenal buffer size is enough. \param host_ptr_arg
   * pointer to buffer to upload \param sizeBytes_arg buffer size
   * */
  void upload(const void * host_ptr_arg, std::size_t sizeBytes_arg);

  /** \brief Uploads data from CPU memory to device array.
   * \note This overload never allocates memory in contrast to the
   * other upload function.
   * \return true if upload successful
   * \param host_ptr_arg pointer to buffer to upload
   * \param device_begin_byte_offset first byte position to upload to
   * \param num_bytes number of bytes to upload
   * */
  bool upload(
    const void * host_ptr_arg, std::size_t device_begin_byte_offset, std::size_t num_bytes);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that intenal buffer size is enough. \param host_ptr_arg
   * pointer to buffer to upload \param sizeBytes_arg buffer size
   * */
  void upload_async(const void * host_ptr_arg, std::size_t sizeBytes_arg);

  /** \brief Downloads data from internal buffer to CPU memory
   * \param host_ptr_arg pointer to buffer to download
   * */

  /** \brief Uploads data from CPU memory to device array.
   * \note This overload never allocates memory in contrast to the
   * other upload function.
   * \return true if upload successful
   * \param host_ptr_arg pointer to buffer to upload
   * \param device_begin_byte_offset first byte position to upload to
   * \param num_bytes number of bytes to upload
   * */
  bool upload_async(
    const void * host_ptr_arg, std::size_t device_begin_byte_offset, std::size_t num_bytes);

  void download(void * host_ptr_arg);

  /** \brief Downloads data from internal buffer to CPU memory.
   * \return true if download successful
   * \param host_ptr_arg pointer to buffer to download
   * \param num_bytes number of bytes to download
   * */
  bool download(void * host_ptr_arg, std::size_t num_bytes);

  /** \brief Downloads data from internal buffer to CPU memory.
   * \return true if download successful
   * \param host_ptr_arg pointer to buffer to download
   * \param num_bytes number of bytes to download
   * */
  bool download_async(void * host_ptr_arg, std::size_t num_bytes);

  /** \brief wait for event in event list to complete
   * */
  void syncEvent();

  /** \brief Attached wait event to the buffer
   * \param DeviceEvent event to wait
   * */
  void setEvent(std::shared_ptr<DeviceEvent> event);

  /** \brief Get a DeviceEvent back to create depedency graph or check event
   * status
   * */
  std::shared_ptr<DeviceEvent> getEvent();

  /** \brief Clear or empty event list from the buffer
   * */
  void clearEvent();

  void clear();

  void updateTempSize(std::size_t size);

  /** \brief Performs swap of data pointed with another device memory.
   * \param other_arg device memory to swap with
   * */
  void swap(DeviceMemory * other_arg);

  /** \brief Returns pointer for internal buffer in GPU memory. */
  template <class T>
  T * ptr()
  {
    return (T *)data_;
  }

  /** \brief Returns constant pointer for internal buffer in GPU memory. */
  template <class T>
  const T * ptr() const
  {
    return (const T *)data_;
  }

  /** \brief Returns true if unallocated otherwise false. */
  bool empty() const;

  std::size_t sizeBytes() const;

private:
  void create_(std::size_t sizeBytes_arg, MemoryType type);

  /** \brief Device pointer. */
  void * data_;

  /** \brief Allocated size in bytes. */
  std::size_t sizeBytes_;

  std::size_t sizeBytesTemp_;

  /** \brief Memory Type. */
  MemoryType type_;

  /** \brief Pointer to reference counter in CPU memory. */
  std::atomic<int> * refcount_;

  /** \brief Device Event */
  std::shared_ptr<DeviceEvent> event_;

  /** \brief HW device from SYCL */
  std::shared_ptr<Device> dev_;
};

///////////////////////////////////////////////////////////////////////////////
/** \brief @b DeviceMemory2D class
 *
 * \note This is a BLOB container class with reference counting for pitched GPU
 * memory.
 *
 * \author Anatoly Baksheev
 */

class SYCL_UTILS_API DeviceMemory2D
{
public:
  /** \brief Empty constructor. */
  DeviceMemory2D();

  /** \brief Destructor. */
  ~DeviceMemory2D();

  /** \brief Allocates internal buffer in GPU memory
   * \param rows_arg number of rows to allocate
   * \param colsBytes_arg width of the buffer in bytes
   * */
  //  DeviceMemory2D(int minor_arg, int majorBytes_arg, StorageOrder order);

  // DeviceMemory2D(uint32_t cols, uint32_t rows, uint32_t element_size,
  // StorageOrder order);

  DeviceMemory2D(uint32_t cols, uint32_t rows, const std::type_info * info, StorageOrder order);

  DeviceMemory2D(
    uint32_t cols, uint32_t rows, const std::type_info * info, StorageOrder order,
    std::shared_ptr<Device> dev);

  /** \brief Initializes with user allocated buffer. Reference counting is
   * disabled in this case. \param rows_arg number of rows \param colsBytes_arg
   * width of the buffer in bytes \param data_arg pointer to buffer \param
   * step_arg stride between two consecutive rows in bytes
   * */
  DeviceMemory2D(int minor_arg, int majorBytes_arg, void * data_arg, std::size_t step_arg);

  /** \brief Copy constructor. Just increments reference counter. */
  DeviceMemory2D(const DeviceMemory2D & other_arg);

  /** \brief Assignment operator. Just increments reference counter. */
  DeviceMemory2D & operator=(const DeviceMemory2D & other_arg);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param rows_arg number of rows to allocate
   * \param colsBytes_arg width of the buffer in bytes
   * */
  void create(uint32_t cols, uint32_t rows);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param rows_arg number of rows to allocate
   * \param colsBytes_arg width of the buffer in bytes
   * \param type Memory type such as shared, device, or host
   * */
  // void
  // create(int minor_arg, int majorBytes_arg, MemoryType type);

  void create(uint32_t cols, uint32_t rows, uint32_t step);

  /** \brief Decrements reference counter and releases internal buffer if
   * needed. */
  void release();

  /** \brief Change the size without reallocate the buffer if the new size is
   * smaller. \param cols, width of the matrix \param rows, height of the matrix
   * */
  void resize(uint32_t cols, uint32_t rows);

  /** \brief Change the size without reallocate the buffer if the new size is
   * smaller. \param cols, width of the matrix \param rows, height of the matrix
   * \param dev, Device contains sycl queue
   * */
  void resize(uint32_t cols, uint32_t rows, std::shared_ptr<Device> dev);

  void updateTempSize(int minor_arg, int majorBytes_arg);

  /** \brief Fill all data with the pattern.
   * \param pattern
   * Explicit specialize template doesn't work.  Declare multiple common types
   * for fill
   * */
  /*
  void fill(float pattern);

  void fill(int pattern);

  void fill(double pattern);

  void fill(uint8_t pattern);
  */

  /** \brief Fill all data with the pattern.
   * \param pattern
   * Explicit specialize template doesn't work.  Declare multiple common types
   * for fill
   * */
  /*
  void fill_async(float pattern);

  void fill_async(int pattern);

  void fill_async(double pattern);

  void fill_async(uint8_t pattern);
  */

  void fill(void * pattern);

  /** \brief Performs data copying. If destination size differs it will be
   * reallocated. \param other destination container
   * */
  void copyTo(DeviceMemory2D & other);

  /** \brief Performs data copying. If destination size differs it will be
   * reallocated. \param other destination container
   * */
  void copyTo(DeviceMemory2D & other,
              const DeviceMemory2D & mask) const;  //, U* dummy);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that intenal buffer size is enough. \param host_ptr_arg
   * pointer to host buffer to upload \param host_step_arg stride between two
   * consecutive rows in bytes for host buffer \param rows_arg number of rows to
   * upload \param colsBytes_arg width of host buffer in bytes
   * */
  void upload(const void * host_ptr_arg, uint32_t host_step_arg, uint32_t cols, uint32_t rows);

  void upload(const void * host_ptr_arg);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that intenal buffer size is enough. \param host_ptr_arg
   * pointer to host buffer to upload \param host_step_arg stride between two
   * consecutive rows in bytes for host buffer \param rows_arg number of rows to
   * upload \param colsBytes_arg width of host buffer in bytes
   * */
  void upload_async(
    const void * host_ptr_arg, uint32_t host_step_arg, uint32_t cols, uint32_t rows);

  void upload_async(const void * host_ptr_arg);

  /** \brief Downloads data from internal buffer to CPU memory. User is
   * responsible for correct host buffer size. \param host_ptr_arg pointer to
   * host buffer to download \param host_step_arg stride between two consecutive
   * rows in bytes for host buffer
   * */
  void download(void * host_ptr_arg, uint32_t host_step_arg, uint32_t cols, uint32_t rows);

  /** \brief Performs swap of data pointed with another device memory.
   * \param other_arg device memory to swap with
   * */
  void swap(DeviceMemory2D * other_arg);

  /** \brief Attached wait event to the buffer
   * \param DeviceEvent event to wait
   * */
  void setEvent(std::shared_ptr<DeviceEvent> event);

  /** \brief Get a DeviceEvent back to create depedency graph or check event
   * status
   * */
  std::shared_ptr<DeviceEvent> getEvent();

  /** \brief Clear or empty event list from the buffer
   * */
  void clearEvent();

  /** \brief wait for event in event list to complete
   * */
  void syncEvent();

  /** \brief multiply with another buffer
   * */
  void mul(DeviceMemory2D * other);

  /** \brief Returns pointer to given row in internal buffer.
   * \param y_arg row index
   * */
  void * ptr(int rows = 0) { return (void *)((char *)data_ + rows * majorBytes_ * elem_size_); }

  /** \brief Returns constant pointer to given row in internal buffer.
   * \param y_arg row index
   * */
  const void * ptr(int rows = 0) const
  {
    return (const void *)((const char *)data_ + rows * majorBytes_ * elem_size_);
  }

  void * ptr(int minor_arg, int major_arg)
  {
    return (void *)((char *)data_ + (major_arg * majorBytes_ * elem_size_ + minor_arg));
    // return (const void *)((char*)data_ + (minor_arg * majorBytes_ *
    // elem_size_ + major_arg));
  }

  const void * ptr(int minor_arg, int major_arg) const
  {
    return (void *)((char *)data_ + (major_arg * majorBytes_ * elem_size_ + minor_arg));
    // return (const void *)((char*)data_ + (minor_arg * majorBytes_ *
    // elem_size_ + major_arg));
  }

  void updateRect(Rect rect) { rect_ = rect; }

  Rect getRect() { return rect_; }

  /** \brief Returns true if unallocated otherwise false. */
  bool empty() const;

  /** \brief Returns number of bytes in each row. */
  int majorBytes() const;

  /** \brief Returns number of rows. */
  int minor() const;

  /** \brief Returns stride between two consecutive rows in bytes for internal
   * buffer. Step is stored always and everywhere in bytes!!! */
  std::size_t step() const;

private:
  void create_(uint32_t step, uint32_t minor, uint32_t majorBytes, MemoryType type);
  /** \brief Device pointer. */

  template <typename U>
  std::shared_ptr<DeviceEvent> copyTo_(
    U * src, U * dst, char * mask, DeviceEvent * maskEvent) const;

  template <typename U>
  std::shared_ptr<DeviceEvent> mul_(U * src, U * dst, DeviceEvent * otherEvent);

  template <typename U>
  std::shared_ptr<DeviceEvent> fill_(U pattern);

  void * data_;

  /** \brief Stride between two consecutive rows in bytes for internal buffer.
   * Step is stored always and everywhere in bytes!!! */
  uint32_t step_;

  /** \brief Number of rows. */
  uint32_t minor_;

  /** \brief Width of the buffer in bytes. */
  uint32_t majorBytes_;

  uint32_t usedMinor_;

  uint32_t usedMajorBytes_;

  uint32_t elem_size_;

  /** \brief Memory Type. */
  MemoryType type_;

  /** \brief Storage Type (Row/Column Major) */
  StorageOrder order_;

  Rect rect_;

  /** \brief Pointer to reference counter in CPU memory. */
  std::atomic<int> * refcount_;

  /** \brief Device Event */
  std::shared_ptr<DeviceEvent> event_;

  /** \brief type info */
  const std::type_info * typeInfo_;

  /** \brief HW device from SYCL */
  std::shared_ptr<Device> dev_;
};

#endif
