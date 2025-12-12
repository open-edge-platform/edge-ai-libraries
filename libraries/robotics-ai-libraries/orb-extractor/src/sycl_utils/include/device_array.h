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
 */
#ifndef __DEVICE_ARRAY_H__
#define __DEVICE_ARRAY_H__

#include <initializer_list>
#include <iterator>
#include <memory>
#include <vector>

#include "device.h"

template <typename T>
class device_iterator;

class DeviceMemory;
class DeviceMemory2D;
struct DeviceEvent;

template <typename T>
class device_pointer
{
protected:
  T * ptr;

public:
  using value_type = T;
  using difference_type = std::make_signed<std::size_t>::type;
  using pointer = T *;
  using reference = T &;
  using const_reference = const T &;
  using iterator_category = std::random_access_iterator_tag;
  //  using is_hetero = std::false_type;         // required
  using is_passed_directly = std::true_type;  // required

  device_pointer(T * p) : ptr(p) {}
  // needed for malloc_device, count is number of bytes to allocate
  device_pointer() {}
  device_pointer & operator=(const device_iterator<T> & in)
  {
    this->ptr = static_cast<device_pointer<T>>(in).ptr;
    return *this;
  }

  // include operators from base class
  device_pointer & operator++()
  {
    ++(this->ptr);
    return *this;
  }
  device_pointer & operator--()
  {
    --(this->ptr);
    return *this;
  }
  device_pointer & operator+=(difference_type forward)
  {
    this->ptr = this->ptr + forward;
    return *this;
  }
  device_pointer & operator-=(difference_type backward)
  {
    this->ptr = this->ptr - backward;
    return *this;
  }
};

template <typename T>
class device_iterator : public device_pointer<T>
{
  using Base = device_pointer<T>;

protected:
  std::size_t idx;

public:
  using value_type = T;
  using difference_type = std::make_signed<std::size_t>::type;
  using pointer = typename Base::pointer;
  using reference = typename Base::reference;
  using iterator_category = std::random_access_iterator_tag;
  using is_passed_directly = std::true_type;  // required

  device_iterator() : Base(nullptr), idx(0) {}
  device_iterator(T * vec, std::size_t index) : Base(vec), idx(index) {}
  /*
  device_iterator &operator=(const device_iterator &in) {
    Base::operator=(in);
    idx = in.idx;
    return *this;
  }
  */

  reference operator*() const { return *(Base::ptr + idx); }

  reference operator[](difference_type i) { return Base::ptr[idx + i]; }
  reference operator[](difference_type i) const { return Base::ptr[idx + i]; }
  device_iterator & operator++()
  {
    ++idx;
    return *this;
  }
  device_iterator & operator--()
  {
    --idx;
    return *this;
  }
  device_iterator operator++(int)
  {
    device_iterator it(*this);
    ++(*this);
    return it;
  }
  device_iterator operator--(int)
  {
    device_iterator it(*this);
    --(*this);
    return it;
  }
  device_iterator operator+(difference_type forward) const
  {
    const auto new_idx = idx + forward;
    return {Base::ptr, new_idx};
  }
  device_iterator & operator+=(difference_type forward)
  {
    idx += forward;
    return *this;
  }
  device_iterator operator-(difference_type backward) const { return {Base::ptr, idx - backward}; }
  device_iterator & operator-=(difference_type backward)
  {
    idx -= backward;
    return *this;
  }
  friend device_iterator operator+(difference_type forward, const device_iterator & it)
  {
    return it + forward;
  }
  difference_type operator-(const device_iterator & it) const { return idx - it.idx; }

  /*
  template <typename OtherIterator>
  typename std::enable_if<internal::is_hetero_iterator<OtherIterator>::value,
                          difference_type>::type
  operator-(const OtherIterator &it) const {
    return idx - it.get_idx();
  }
  */

  bool operator==(const device_iterator & it) const { return *this - it == 0; }
  bool operator!=(const device_iterator & it) const { return !(*this == it); }
  bool operator<(const device_iterator & it) const { return *this - it < 0; }
  bool operator>(const device_iterator & it) const { return it < *this; }
  bool operator<=(const device_iterator & it) const { return !(*this > it); }
  bool operator>=(const device_iterator & it) const { return !(*this < it); }

  std::size_t get_idx() const { return idx; }  // required

  device_iterator & get_buffer() { return *this; }  // required

  std::size_t size() const { return idx; }
};

//////////////////////////////////////////////////////////////////////////////
/** \brief @b DeviceArray class
 *
 * \note Typed container for GPU memory with reference counting.
 *
 * \author Anatoly Baksheev
 */
template <typename T>
class DeviceArray
{
public:
  /** \brief Element type. */
  using iterator = device_iterator<T>;
  using const_iterator = const iterator;
  using type = T;
  using reference = T &;
  using difference_type = std::make_signed<std::size_t>::type;

  /** \brief Element size. */
  enum
  {
    elem_size = sizeof(T)
  };

  /** \brief Empty constructor. */
  DeviceArray();

  /** \brief Empty destructor. */
  ~DeviceArray();

  /** \brief Constructor with device */
  DeviceArray(std::shared_ptr<Device> dev);

  /** \brief Constructor to allocate buffer based on size
   * \param size number of elements to allocate
   * */
  DeviceArray(std::size_t size);

  /** \brief Constructor to allocate buffer based on size and device type
   * \param size number of elements to allocate
   * \param type allocate buffer from Device declare earlier
   * */
  DeviceArray(std::size_t size, std::shared_ptr<Device> dev);

  /** \brief Constructor to allocate buffer based on size and device type
   * \param size number of elements to allocate
   * \param type allocate buffer from Device declare earlier
   * */
  DeviceArray(std::size_t size, DeviceType type);

  /** \brief Initializes with user allocated buffer. Reference counting is
   * disabled in this case. \param ptr pointer to buffer \param size elements
   * number
   * */
  DeviceArray(void * ptr, std::size_t size);

  /** \brief Allocates internal buffer based on memory type
   * \param size number of elements to allocate
   * \param type Memory type such as shared, device, or host
   * */
  DeviceArray(std::size_t size, MemoryType type);

  /** \brief Copy constructor. Just increments reference counter. */
  DeviceArray(const DeviceArray & other);

  /** \brief Assignment operator. Just increments reference counter. */
  DeviceArray & operator=(const DeviceArray & other);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param size elements number
   * */
  void create(std::size_t size);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param size elements number \param dev use
   * specific dev to alloc memory
   * */
  void create(std::size_t size, std::shared_ptr<Device> dev);

  /** \brief Change the size without reallocate the buffer if the new size is
   * smaller. \param size elements number
   * */
  void resize(std::size_t size);

  /** \brief Change the size without reallocate the buffer if the new size is
   * smaller. \param size elements number \param dev use specific dev to alloc
   * memory
   * */
  void resize(std::size_t size, std::shared_ptr<Device> dev);

  /** \brief Decrements reference counter and releases internal buffer if
   * needed. */
  void release();

  /** \brief Performs data copying. If destination size differs it will be
   * reallocated. \param other destination container
   * */
  void copyTo(DeviceArray & other);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that internal buffer size is enough. \param host_ptr
   * pointer to buffer to upload \param size elements number
   * */
  void upload(const T * host_ptr, std::size_t size);

  /** \brief Uploads data from CPU memory to internal buffer.
   * \return true if upload successful
   * \note In contrast to the other upload function, this function
   * never allocates memory.
   * \param host_ptr pointer to buffer to upload
   * \param device_begin_offset begin upload
   * \param num_elements number of elements from device_begin_offset
   * */
  bool upload(const T * host_ptr, std::size_t device_begin_offset, std::size_t num_elements);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that internal buffer size is enough.  No wait and return
   * \param host_ptr pointer to buffer to upload
   * \param size elements number
   * */
  void upload_async(const T * host_ptr, std::size_t size);

  /** \brief Uploads data from CPU memory to internal buffer.
   * \return true if upload successful
   * \note In contrast to the other upload function, this function
   * never allocates memory.
   * \param host_ptr pointer to buffer to upload
   * \param device_begin_offset begin upload
   * \param num_elements number of elements from device_begin_offset
   * */
  bool upload_async(const T * host_ptr, std::size_t device_begin_offset, std::size_t num_elements);

  /** \brief Downloads data from internal buffer to CPU memory
   * \param host_ptr pointer to buffer to download
   * */
  void download(T * host_ptr) const;

  /** \brief Downloads data from internal buffer to CPU memory.
   * \return true if download successful
   * \param host_ptr pointer to buffer to download
   * \param device_begin_offset begin download location
   * \param num_elements number of elements from device_begin_offset
   * */
  bool download(T * host_ptr, std::size_t size) const;

  /** \brief Downloads data from internal buffer to CPU memory.
   * \return true if download successful
   * \param host_ptr pointer to buffer to download
   * \param device_begin_offset begin download location
   * \param num_elements number of elements from device_begin_offset
   * */
  bool download_async(T * host_ptr, std::size_t size) const;

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that internal buffer size is enough. \param data host
   * vector to upload from
   * */
  template <class A>
  void upload(const std::vector<T, A> & data);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that internal buffer size is enough. \param data host
   * vector to upload from
   * */
  template <class A>
  void upload_async(const std::vector<T, A> & data);

  /** \brief Downloads data from internal buffer to CPU memory
   * \param data  host vector to download to
   * */
  //  template <typename A>
  void download(std::vector<T> & data) const;

  /** \brief Downloads data from internal buffer to CPU memory
   * \param data  host vector to download to
   * */
  //  template <typename A>
  void download(std::vector<T> & data, std::size_t size) const;

  /** \brief The device array may allocate more buffer.  Reduce extra buffer
   * size \param size size of the buffer to keep
   * */
  void compact(std::size_t size);

  /** \brief Wait till all events synchronize
   * */
  void sync() const;

  /** \brief Attached wait event to the buffer
   * \param DeviceEvent event to wait
   * */
  void setEvent(std::shared_ptr<DeviceEvent> event) const;

  /** \brief Get a DeviceEvent back to create dependency graph or check event
   * status
   * */
  std::shared_ptr<DeviceEvent> getEvent() const;

  /** \brief Clear or empty event list from the buffer
   * */
  void clearEvent() const;

  /** \brief Clear all the content of the array
   * */
  void clear();

  /** \brief Check if the device array is empty or size of 0
   * */
  bool empty();

  void fill(T pattern);

  void fill_async(T pattern);

  void insert(device_iterator<T> position, std::size_t n, const T & x) {};

  reference front() const { return *begin(); }

  reference front() { return *begin(); }

  reference back(void) const { return (data()[size() - 1]); }

  reference back(void) { return (data()[size() - 1]); }

  /** \brief Performs swap of data pointed with another device array.
   * \param other_arg device array to swap with
   * */
  void swap(DeviceArray & other_arg);

  /** \brief Returns pointer for internal buffer in GPU memory. */
  T * data();

  /** \brief Returns const pointer for internal buffer in GPU memory. */
  const T * data() const;

  // using DeviceMemory::ptr;

  /** \brief Returns pointer for internal buffer in GPU memory. */
  operator T *();

  /** \brief Returns const pointer for internal buffer in GPU memory. */
  operator const T *() const;

  /** \brief Returns size in elements. */
  std::size_t size() const;

  iterator begin() noexcept { return device_iterator<T>(&data()[0], 0); }
  iterator end() { return device_iterator<T>(&data()[0], size()); }

private:
  DeviceMemory * mem_;
};

///////////////////////////////////////////////////////////////////////////////
/** \brief @b DeviceArray2D class
 *
 * \note Typed container for pitched GPU memory with reference counting.
 *
 * \author Anatoly Baksheev
 */
template <
  typename T,
  StorageOrder Order = ROW_MAJOR>  //, int Cols = 0, int Rows = 0>
class DeviceMatrix
{
public:
  /** \brief Element type. */
  using type = T;

  /** \brief Element size. */
  enum
  {
    elem_size = sizeof(T)
  };

  /** \brief Empty constructor. */
  DeviceMatrix();

  /** \brief Empty constructor. */
  // DeviceMatrix(StorageOrder order = ROW_MAJOR);

  /** \brief Empty destructor. */
  ~DeviceMatrix();

  /** \brief Constructor with device type */
  DeviceMatrix(std::shared_ptr<Device> dev);

  /** \brief Allocates internal buffer in GPU memory
   * \param rows number of rows to allocate
   * \param cols number of elements in each row
   * \param order = based on column major or row major
   * */
  DeviceMatrix(uint32_t rows, uint32_t cols, StorageOrder order = Order);

  /** \brief Allocates internal buffer in GPU memory
   * \param rows number of rows to allocate
   * \param cols number of elements in each row
   * \param order = based on column major or row major
   * */
  DeviceMatrix(uint32_t rows, uint32_t cols, std::shared_ptr<Device> dev);

  /** \brief Allocates internal buffer in GPU memory
   * \param rows number of rows to allocate
   * \param cols number of elements in each row
   * \param pattern, initialize with a pattern
   * */
  DeviceMatrix(uint32_t rows, uint32_t cols, T pattern);

  /** \brief Allocates internal buffer in GPU memory
   * \param Initialize 3x1 vector
   * */
  DeviceMatrix(T arg1, T arg2, T arg3);

  /** \brief Allocates internal buffer in GPU memory
   * \param initialize list to initialize this matrix.  Support rows = 1 for now
   * */
  DeviceMatrix(std::initializer_list<T> initList);

  /** \brief Initializes with user allocated buffer. Reference counting is
   * disabled in this case. \param rows number of rows \param cols number of
   * elements in each row \param data pointer to buffer \param stepBytes stride
   * between two consecutive rows in bytes
   * */
  DeviceMatrix(uint32_t rows, uint32_t cols, void * data, std::size_t stepBytes);

  DeviceMatrix(Rect rect, const DeviceMatrix & source);

  /** \brief Copy constructor. Just increments reference counter. */
  DeviceMatrix(const DeviceMatrix & other);

  /** \brief Assignment operator. Just increments reference counter. */
  DeviceMatrix & operator=(const DeviceMatrix & other);

  /** \brief Returns number of elements in each row. */
  int cols() const;

  /** \brief Returns number of rows. */
  int rows() const;

  /** \brief Returns step in elements. */
  std::size_t elem_step() const;

  /** \brief Returns step in elements. */
  std::size_t step() const;

  /** \brief Returns rect for the buffer. */
  Rect getRect() const;

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param rows number of rows to allocate
   * \param cols number of elements in each row
   * */
  void create(uint32_t rows, uint32_t cols);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param rows number of rows to allocate
   * \param cols number of elements in each row
   * \param initialize with a pattern
   * */
  void create(uint32_t rows, uint32_t cols, T pattern);

  /** \brief Allocates internal buffer in GPU memory. If internal buffer was
   * created before the function recreates it with new size. If new and old
   * sizes are equal it does nothing. \param rows number of rows to allocate
   * \param cols number of elements in each row
   * \param type Memory type such as shared, device, or host
   * */
  void create(uint32_t rows, uint32_t cols, MemoryType type);

  void resize(uint32_t rows, uint32_t cols);

  void resize(uint32_t rows, uint32_t cols, std::shared_ptr<Device> dev);

  void fill(T pattern);

  // void fill_async(void* pattern);

  /** \brief Decrements reference counter and releases internal buffer if
   * needed. */
  void release();

  /** \brief Performs data copying. If destination size differs it will be
   * reallocated. \param other destination container
   * */
  void copyTo(DeviceMatrix & other);

  /** \brief Performs data copying. If destination size differs it will be
   * reallocated. \param other destination container
   * */
  void copyTo(DeviceMatrix & other, const DeviceMatrix<char> & mask);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that internal buffer size is enough. \param host_ptr
   * pointer to host buffer to upload \param host_step stride between two
   * consecutive rows in bytes for host buffer \param rows number of rows to
   * upload \param cols number of elements in each row
   * */
  void upload(const void * host_ptr, uint32_t host_step, uint32_t cols, uint32_t rows);

  void upload(const void * host_ptr);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that internal buffer size is enough. \param host_ptr
   * pointer to host buffer to upload \param host_step stride between two
   * consecutive rows in bytes for host buffer \param rows number of rows to
   * upload \param cols number of elements in each row
   * */
  void upload_async(const void * host_ptr, std::size_t host_step, int cols, int rows);

  void upload_async(const void * host_ptr);

  /** \brief Downloads data from internal buffer to CPU memory. User is
   * responsible for correct host buffer size. \param host_ptr pointer to host
   * buffer to download \param host_step stride between two consecutive rows in
   * bytes for host buffer
   * */
  void download(void * host_ptr, uint32_t host_step, uint32_t cols, uint32_t rows);

  /** \brief Performs swap of data pointed with another device array.
   * \param other_arg device array to swap with
   * */
  void swap(DeviceMatrix & other_arg);

  /** \brief Uploads data to internal buffer in GPU memory. It calls create()
   * inside to ensure that internal buffer size is enough. \param data host
   * vector to upload from \param cols stride in elements between two
   * consecutive rows for host buffer
   * */
  template <class A>
  void upload(const std::vector<T, A> & data, int rows);

  /** \brief Downloads data from internal buffer to CPU memory
   * \param data host vector to download to
   * \param cols Output stride in elements between two consecutive rows for host
   * vector.
   * */
  template <class A>
  void download(std::vector<T, A> & data, int & rows);

  /** \brief The device array may allocate more buffer.  Reduce extra buffer
   * size \param size size of the buffer to keep
   * */
  void compact(int cols, int rows);

  /** \brief Wait till all events synchronize
   * */
  void sync() const;

  /** \brief Attached wait event to the buffer
   * \param DeviceEvent event to wait
   * */
  void setEvent(std::shared_ptr<DeviceEvent> event) const;

  /** \brief Get a DeviceEvent back to create dependency graph or check event
   * status
   * */
  std::shared_ptr<DeviceEvent> getEvent() const;

  /** \brief Clear or empty event list from the buffer
   * */
  void clearEvent() const;

  /** \brief multiple with another matrix
   * */
  void mul(DeviceMatrix * other) const;

  /** \brief Return size, width and height for the buffer
   * */
  Size size() const;

  /** \brief Check if the device array is empty or size of 0
   * */
  bool empty() const;

  /** \brief Returns pointer to given row in internal buffer.
   * \param sync - if the data has event attached, wait for it to complete
   * */
  T * data(bool sync = false);

  /** \brief Returns const pointer to given row in internal buffer.
   * \param y row index
   * */
  const T * data(bool sync = false) const;

  T * row(int y = 0);

  T * col(int y = 0);

  const T * col(int y = 0) const;

  /**
   * Operator that returns a (pointer to a) row of the data.
   */
  const T & operator[](size_t index) const;

  /**
   * Operator that returns reference to the data based on row and col
   */
  T & operator()(size_t row, size_t col);

  /**
   * Operator that returns reference to the data based on row and col
   */
  const T & operator()(size_t row, size_t col) const;

  /** \brief Returns pointer for internal buffer in GPU memory. */
  operator T *();

  /** \brief Returns const pointer for internal buffer in GPU memory. */
  operator const T *() const;

  DeviceMatrix<T> operator()(Rect rect) const;

  DeviceMemory2D * getMem() const { return mem_; }

private:
  DeviceMemory2D * mem_;
  StorageOrder order_;
  uint32_t rows_;
  uint32_t cols_;
};

#include "device_array.hpp"

#endif
