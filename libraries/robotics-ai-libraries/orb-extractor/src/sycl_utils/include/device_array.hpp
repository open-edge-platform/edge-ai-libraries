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
#include <cstring>

#include "device_array.h"
#include "device_memory.h"

#pragma once

#ifndef __DEVICE_ARRAY_HPP__
#define __DEVICE_ARRAY_HPP__

///////////////////  Inline implementations of DeviceArray2D //////////////////
//
template <typename T>
inline DeviceArray<T>::DeviceArray()
{
  mem_ = new DeviceMemory();
}

template <typename T>
inline DeviceArray<T>::~DeviceArray()
{
  mem_->release();
  free(mem_);
}

template <typename T>
inline DeviceArray<T>::DeviceArray(std::shared_ptr<Device> dev)
{
  mem_ = new DeviceMemory(dev);
}

template <typename T>
inline DeviceArray<T>::DeviceArray(std::size_t size)
{
  mem_ = new DeviceMemory(size * elem_size);
}

template <typename T>
inline DeviceArray<T>::DeviceArray(std::size_t size, std::shared_ptr<Device> dev)
{
  mem_ = new DeviceMemory(size * elem_size, dev);
}

template <typename T>
inline DeviceArray<T>::DeviceArray(std::size_t size, DeviceType type)
{
  mem_ = new DeviceMemory(size * elem_size, type);
}

template <typename T>
inline DeviceArray<T>::DeviceArray(void * ptr, std::size_t size)
{
  mem_ = new DeviceMemory(ptr, size * elem_size);
}

template <typename T>
inline DeviceArray<T>::DeviceArray(std::size_t size, MemoryType type)
{
  mem_ = new DeviceMemory(size * elem_size, type);
}

template <typename T>
inline DeviceArray<T>::DeviceArray(const DeviceArray & other)
{
  mem_ = new DeviceMemory(*other.mem_);
}

template <typename T>
inline DeviceArray<T> & DeviceArray<T>::operator=(const DeviceArray & other)
{
  mem_ = new DeviceMemory(*other.mem_);
  return *this;
}

template <typename T>
inline void DeviceArray<T>::create(std::size_t size)
{
  mem_->create(size * elem_size);
}

template <typename T>
inline void DeviceArray<T>::create(std::size_t size, std::shared_ptr<Device> dev)
{
  mem_->create(size * elem_size, dev);
}

template <typename T>
inline void DeviceArray<T>::resize(std::size_t size)
{
  mem_->resize(size * elem_size);
}

template <typename T>
inline void DeviceArray<T>::resize(std::size_t size, std::shared_ptr<Device> dev)
{
  mem_->resize(size * elem_size, dev);
}

template <typename T>
inline void DeviceArray<T>::release()
{
  mem_->release();
  free(mem_);
}

template <typename T>
inline void DeviceArray<T>::copyTo(DeviceArray & other)
{
  // TODO FIXME
  // mem_->copyTo(other.mem_);
}

template <typename T>
inline void DeviceArray<T>::upload(const T * host_ptr, std::size_t size)
{
  mem_->upload(host_ptr, size * elem_size);
}

template <typename T>
inline bool DeviceArray<T>::upload(
  const T * host_ptr, std::size_t device_begin_offset, std::size_t num_elements)
{
  std::size_t begin_byte_offset = device_begin_offset * elem_size;
  std::size_t num_bytes = num_elements * elem_size;
  return mem_->upload(host_ptr, begin_byte_offset, num_bytes);
}

template <typename T>
inline void DeviceArray<T>::upload_async(const T * host_ptr, std::size_t size)
{
  mem_->upload_async(host_ptr, size * elem_size);
}

template <typename T>
inline bool DeviceArray<T>::upload_async(
  const T * host_ptr, std::size_t device_begin_offset, std::size_t num_elements)
{
  std::size_t begin_byte_offset = device_begin_offset * elem_size;
  std::size_t num_bytes = num_elements * elem_size;
  return mem_->upload_async(host_ptr, begin_byte_offset, num_bytes);
}

template <typename T>
inline void DeviceArray<T>::download(T * host_ptr) const
{
  mem_->download(host_ptr);
}

template <typename T>
inline bool DeviceArray<T>::download(T * host_ptr, std::size_t num_elements) const
{
  std::size_t num_bytes = num_elements * elem_size;
  return mem_->download(host_ptr, num_bytes);
}

template <typename T>
inline bool DeviceArray<T>::download_async(T * host_ptr, std::size_t num_elements) const
{
  std::size_t num_bytes = num_elements * elem_size;
  return mem_->download_async(host_ptr, num_bytes);
}

template <typename T>
inline void DeviceArray<T>::sync() const
{
  mem_->syncEvent();
}

template <typename T>
inline void DeviceArray<T>::setEvent(std::shared_ptr<DeviceEvent> event) const
{
  mem_->setEvent(event);
}

template <typename T>
inline std::shared_ptr<DeviceEvent> DeviceArray<T>::getEvent() const
{
  return mem_->getEvent();
}

template <typename T>
inline void DeviceArray<T>::clearEvent() const
{
  mem_->clearEvent();
}

template <typename T>
inline void DeviceArray<T>::clear()
{
  mem_->clear();
}

template <typename T>
inline bool DeviceArray<T>::empty()
{
  return size() > 0 ? false : true;
}

template <typename T>
inline void DeviceArray<T>::swap(DeviceArray & other_arg)
{
  // mem_->swap(other_arg.mem_);

  DeviceMemory * tmp_mem;

  tmp_mem = mem_;
  mem_ = other_arg.mem_;
  other_arg.mem_ = tmp_mem;
  ;
}

template <typename T>
inline DeviceArray<T>::operator T *()
{
  return data();
}

template <typename T>
inline DeviceArray<T>::operator const T *() const
{
  return data();
}

template <typename T>
inline std::size_t DeviceArray<T>::size() const
{
  return mem_->sizeBytes() / elem_size;
}

template <typename T>
inline T * DeviceArray<T>::data()
{
  return mem_->ptr<T>();
}

template <typename T>
inline const T * DeviceArray<T>::data() const
{
  return mem_->ptr<T>();
}

template <typename T>
template <typename A>
inline void DeviceArray<T>::upload(const std::vector<T, A> & data)
{
  upload(&data[0], data.size());
}

template <typename T>
template <typename A>
inline void DeviceArray<T>::upload_async(const std::vector<T, A> & data)
{
  upload_async(&data[0], data.size());
}

template <typename T>
void DeviceArray<T>::download(std::vector<T> & data) const
{
  data.resize(size());
  if (!data.empty()) download(data.data());
}

template <typename T>
void DeviceArray<T>::download(std::vector<T> & data, std::size_t size) const
{
  data.resize(size);
  if (!data.empty()) download(data.data(), size);
}

template <typename T>
inline void DeviceArray<T>::compact(std::size_t size)
{
  mem_->updateTempSize(size * elem_size);
}

template <typename T>
inline void DeviceArray<T>::fill(T pattern)
{
  mem_->fill(pattern);
}

template <typename T>
inline void DeviceArray<T>::fill_async(T pattern)
{
  mem_->fill_async(pattern);
}
///////////////////  Inline implementations of DeviceMatrix //////////////////
template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix()
{
  order_ = Order;

  cols_ = 0;
  rows_ = 0;

  mem_ = new DeviceMemory2D(cols_, rows_, &typeid(T), order_);
}

/*
template <typename T, StorageOrder Order> inline
DeviceMatrix<T, Order>::DeviceMatrix(StorageOrder order)
{
  if ((order == ROW_MAJOR) && (Order == COLUMN_MAJOR))
  {
    order_ = Order;
  }
  else
    order_ = order;

  cols_ = 0;
  rows_ = 0;

  mem_ = new DeviceMemory2D(cols_, rows_, &typeid(T), order);
}
*/

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::~DeviceMatrix()
{
  mem_->release();
  free(mem_);
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(std::shared_ptr<Device> dev)
{
  cols_ = 0;
  rows_ = 0;

  mem_ = new DeviceMemory2D(cols_, rows_, &typeid(T), Order, dev);
}

/*
template <typename T, int Cols, int Rows> inline
DeviceMatrix<T, Cols, Rows>::DeviceMatrix(Device& dev) : rows_(Rows),
cols_(Cols)
{
  order_ = COLUMN_MAJOR;
  mem_ = new DeviceMemory2D(cols_, rows_, &typeid(T), dev);
}
*/

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(uint32_t rows, uint32_t cols, StorageOrder order)
: rows_(rows), cols_(cols)
{
  order_ = order;

  mem_ = new DeviceMemory2D(cols, rows, &typeid(T), order_);
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(
  uint32_t rows, uint32_t cols, std::shared_ptr<Device> dev)
: rows_(rows), cols_(cols)
{
  order_ = Order;

  mem_ = new DeviceMemory2D(cols, rows, &typeid(T), order_, dev);
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(uint32_t rows, uint32_t cols, T pattern)
: rows_(rows), cols_(cols)
{
  order_ = Order;

  mem_ = new DeviceMemory2D(cols, rows, &typeid(T), order_);

  void * pattern_;
  std::memcpy(&pattern_, &pattern, sizeof(T));
  mem_->fill(pattern_);
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(T arg1, T arg2, T arg3) : rows_(1), cols_(3)
{
  order_ = ROW_MAJOR;

  mem_ = new DeviceMemory2D(cols_, rows_, &typeid(T), order_);

  T * data = (T *)mem_->ptr(0);
  data[0] = arg1;
  data[1] = arg2;
  data[2] = arg3;
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(std::initializer_list<T> initList)
: rows_(1), cols_(initList.size())
{
  mem_ = new DeviceMemory2D(cols_, rows_, &typeid(T), order_);

  mem_->upload(initList.begin(), initList.size() * elem_size, 1, initList.size() * elem_size);
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(
  uint32_t rows, uint32_t cols, void * data, std::size_t stepBytes)
: rows_(rows), cols_(cols)
{
  order_ = ROW_MAJOR;
  mem_ = new DeviceMemory2D(cols, rows * elem_size, data, stepBytes);
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(Rect rect, const DeviceMatrix & source)
{
  order_ = source.order_;
  mem_ = new DeviceMemory2D(*source.mem_);
  mem_->updateRect(rect);
  cols_ = source.cols_;
  rows_ = source.rows_;
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::DeviceMatrix(const DeviceMatrix & other)
{
  mem_ = new DeviceMemory2D(*other.mem_);

  rows_ = other.rows_;
  cols_ = other.cols_;
  order_ = other.order_;
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order> & DeviceMatrix<T, Order>::operator=(const DeviceMatrix & other)
{
  mem_ = new DeviceMemory2D(*other.mem_);
  return *this;
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::create(uint32_t rows, uint32_t cols)
{
  rows_ = rows;
  cols_ = cols;

  mem_->create(cols, rows);
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::create(uint32_t rows, uint32_t cols, T pattern)
{
  rows_ = rows;
  cols_ = cols;

  mem_->create(cols, rows);

  void * pattern_;
  std::memcpy(&pattern_, &pattern, sizeof(T));
  mem_->fill(pattern_);
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::create(uint32_t rows, uint32_t cols, MemoryType type)
{
  rows_ = rows;
  cols_ = cols;

  mem_->create(cols, rows, type);
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::resize(uint32_t rows, uint32_t cols)
{
  if (rows == rows_ && cols == cols_) return;

  mem_->resize(cols, rows);

  rows_ = rows;
  cols_ = cols;
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::resize(
  uint32_t rows, uint32_t cols, std::shared_ptr<Device> dev)
{
  if (rows == rows_ && cols == cols_) return;

  mem_->resize(cols, rows, dev);

  rows_ = rows;
  cols_ = cols;
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::fill(T pattern)
{
  void * pattern_;
  std::memcpy(&pattern_, &pattern, sizeof(T));
  mem_->fill(pattern_);
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::release()
{
  mem_->release();
  free(mem_);
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::copyTo(DeviceMatrix & other)
{
  mem_->copyTo(*other.getMem());
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::copyTo(DeviceMatrix & other, const DeviceMatrix<char> & mask)
{
  // mem_->copyTo(*other.getMem(), *mask.getMem(), static_cast<T*>(nullptr));
  mem_->copyTo(*other.getMem(), *mask.getMem());
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::upload(
  const void * host_ptr, uint32_t host_step, uint32_t cols, uint32_t rows)
{
  if (Order == ROW_MAJOR)
    mem_->upload(host_ptr, host_step, cols, rows);
  else {
    throw std::invalid_argument("Unsupported upload for column major matrix");
  }
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::upload(const void * host_ptr)
{
  if (Order == ROW_MAJOR)
    mem_->upload(host_ptr);
  else {
    throw std::invalid_argument("Unsupported upload for column major matrix");
  }
}

// Remove this in future
template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::upload_async(
  const void * host_ptr, std::size_t host_step, int rows, int cols)
{
  if (Order == ROW_MAJOR)
    return mem_->upload_async(host_ptr, host_step, cols, rows);
  else {
    throw std::invalid_argument("Unsupported upload for column major matrix");
  }
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::upload_async(const void * host_ptr)
{
  if (Order == ROW_MAJOR)
    mem_->upload_async(host_ptr);
  else {
    throw std::invalid_argument("Unsupported upload for column major matrix");
  }
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::download(
  void * host_ptr, uint32_t host_step, uint32_t cols, uint32_t rows)
{
  if (Order == ROW_MAJOR)
    mem_->download(host_ptr, host_step, cols, rows);
  else {
    throw std::invalid_argument("Unsupported download for column major matrix");
  }
}

template <typename T, StorageOrder Order>
template <typename A>
inline void DeviceMatrix<T, Order>::upload(const std::vector<T, A> & data, int cols)
{
  if (Order == ROW_MAJOR)
    upload(&data[0], cols * elem_size, data.size() / cols, cols);
  else {
    throw std::invalid_argument("Unsupported upload for column major matrix");
  }
}

template <typename T, StorageOrder Order>
template <typename A>
inline void DeviceMatrix<T, Order>::download(std::vector<T, A> & data, int & elem_step)
{
  elem_step = cols();
  data.resize(cols() * rows());
  if (!data.empty()) download(&data[0], mem_->majorBytes());
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::swap(DeviceMatrix & other_arg)
{
  mem_->swap(other_arg.mem_);
}

template <typename T, StorageOrder Order>
inline T * DeviceMatrix<T, Order>::data(bool sync)
{
  if (sync) mem_->syncEvent();

  return (T *)mem_->ptr(0);
}

template <typename T, StorageOrder Order>
inline const T * DeviceMatrix<T, Order>::data(bool sync) const
{
  if (sync) mem_->syncEvent();

  return (const T *)mem_->ptr(0);
}

template <typename T, StorageOrder Order>
inline T * DeviceMatrix<T, Order>::row(int y)
{
  return (T *)mem_->ptr(y);
}

template <typename T, StorageOrder Order>
inline T * DeviceMatrix<T, Order>::col(int x)
{
  // TODO: FIXME
  return (T *)mem_->ptr(x);
}

template <typename T, StorageOrder Order>
inline const T * DeviceMatrix<T, Order>::col(int x) const
{
  // TODO: FIXME
  return (T *)mem_->ptr(x);
}

template <typename T, StorageOrder Order>
inline const T & DeviceMatrix<T, Order>::operator[](size_t index) const
{
  T * data = (T *)mem_->ptr(0);
  return data[index];
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::operator T *()
{
  return mem_->ptr();
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T, Order>::operator const T *() const
{
  return mem_->ptr();
}

template <typename T, StorageOrder Order>
inline int DeviceMatrix<T, Order>::cols() const
{
  return cols_;
}

template <typename T, StorageOrder Order>
inline int DeviceMatrix<T, Order>::rows() const
{
  return rows_;
}

template <typename T, StorageOrder Order>
inline std::size_t DeviceMatrix<T, Order>::elem_step() const
{
  return mem_->step() / elem_size;
}

template <typename T, StorageOrder Order>
inline std::size_t DeviceMatrix<T, Order>::step() const
{
  return mem_->step();
}

template <typename T, StorageOrder Order>
inline Rect DeviceMatrix<T, Order>::getRect() const
{
  return mem_->getRect();
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::sync() const
{
  mem_->syncEvent();
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::setEvent(std::shared_ptr<DeviceEvent> event) const
{
  mem_->setEvent(event);
}

template <typename T, StorageOrder Order>
inline std::shared_ptr<DeviceEvent> DeviceMatrix<T, Order>::getEvent() const
{
  return mem_->getEvent();
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::clearEvent() const
{
  mem_->clearEvent();
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::mul(DeviceMatrix * other) const
{
  if (rows_ == other->rows() && cols_ == other->cols()) {
    mem_->mul(other->getMem());
  }
}

template <typename T, StorageOrder Order>
inline Size DeviceMatrix<T, Order>::size() const
{
  Size cur_size = {cols_, rows_};

  return cur_size;
}

template <typename T, StorageOrder Order>
inline bool DeviceMatrix<T, Order>::empty() const
{
  return ((cols_ > 0) && (rows_ > 0)) ? false : true;
}

template <typename T, StorageOrder Order>
inline void DeviceMatrix<T, Order>::compact(int col, int row)
{
  mem_->updateTempSize(col, row * elem_size);
}

template <typename T, StorageOrder Order>
inline T & DeviceMatrix<T, Order>::operator()(size_t row, size_t col)
{
  if (row < 0 || row > rows_ || col < 0 || col > cols_) {
    throw std::out_of_range("Index out of bounds!!");
  }

  /*
  auto event = mem_->getEvent();
  if (event)
  {
    mem_->syncEvent();
    mem_->clearEvent();
  }
  */

  if (order_ == ROW_MAJOR) {
    T * data = (T *)mem_->ptr(row);
    return data[col];
  } else {
    T * data = (T *)mem_->ptr(col);
    return data[row];
  }
}

template <typename T, StorageOrder Order>
inline const T & DeviceMatrix<T, Order>::operator()(size_t row, size_t col) const
{
  if (row < 0 || row > rows_ || col < 0 || col > cols_) {
    throw std::out_of_range("Index out of bounds!!");
  }

  /*
  auto event = mem_->getEvent();
  if (event)
  {
    mem_->syncEvent();
    mem_->clearEvent();
  }
  */

  if (order_ == ROW_MAJOR) {
    T * data = (T *)mem_->ptr(row);
    return data[col];
  } else {
    T * data = (T *)mem_->ptr(col);
    return data[row];
  }
}

template <typename T, StorageOrder Order>
inline DeviceMatrix<T> DeviceMatrix<T, Order>::operator()(Rect rect) const
{
  return DeviceMatrix(rect, *this);
}

#endif /* __DEVICE_ARRAY_HPP__ */
