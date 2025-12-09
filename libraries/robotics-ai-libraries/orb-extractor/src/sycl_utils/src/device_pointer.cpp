// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include <sycl/sycl.hpp>

template <typename T>
class device_iterator;

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
  //  using is_hetero = std::false_type;         // required
  using is_passed_directly = std::true_type;                                // required
  static constexpr sycl::access_mode mode = sycl::access_mode::read_write;  // required

  device_iterator() : Base(nullptr), idx(0) {}
  device_iterator(T * vec, std::size_t index) : Base(vec), idx(index) {}
  template <sycl::access_mode inMode>
  device_iterator(const device_iterator<T> & in) : Base(in.ptr), idx(in.idx)
  {
  }  // required for iter_mode
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
