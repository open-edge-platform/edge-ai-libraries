// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions
// and limitations under the License.

#pragma once

#define NOMINMAX

#include <algorithm>
#include <fstream>
#include <iterator>
#include <iostream>
#include <vector>
#include <cstring>
#include <array>
#include <bitset>

namespace cm_utils {

template <typename T>
std::vector<T> read_binary_file(const char *fname, size_t num = 0) {
  std::vector<T> vec;
  std::ifstream ifs(fname, std::ios::in | std::ios::binary);
  if (ifs.good()) {
    ifs.unsetf(std::ios::skipws);
    std::streampos file_size;
    ifs.seekg(0, std::ios::end);
    file_size = ifs.tellg();
    ifs.seekg(0, std::ios::beg);
    size_t max_num = file_size / sizeof(T);
    vec.resize(num ? (std::min)(max_num, num) : max_num);
    ifs.read(reinterpret_cast<char *>(vec.data()), vec.size() * sizeof(T));
  }
  return vec;
}

template <typename T, template <typename, typename> typename Container, typename Allocator>
bool write_binary_file(const char *fname, const Container<T, Allocator> &vec,
                       size_t num = 0) {
  std::ofstream ofs(fname, std::ios::out | std::ios::binary);
  if (ofs.good()) {
    ofs.write(reinterpret_cast<const char *>(&vec[0]),
              (num ? num : vec.size()) * sizeof(T));
    ofs.close();
  }
  return !ofs.bad();
}

template <typename T>
bool cmp_binary_files(const char *fname1, const char *fname2, T tolerance) {
  const auto vec1 = read_binary_file<T>(fname1);
  const auto vec2 = read_binary_file<T>(fname2);
  if (vec1.size() != vec2.size()) {
    std::cerr << fname1 << " size is " << vec1.size();
    std::cerr << " whereas " << fname2 << " size is " << vec2.size() << std::endl;
    return false;
  }
  for (size_t i = 0; i < vec1.size(); i++) {
    if (abs(vec1[i] - vec2[i]) > tolerance) {
      std::cerr << "Mismatch at " << i << ' ';
      if (sizeof(T) == 1) {
        std::cerr << (int)vec1[i] << " vs " << (int)vec2[i] << std::endl;
      } else {
        std::cerr << vec1[i] << " vs " << vec2[i] << std::endl;
      }
      return false;
    }
  }
  return true;
}

// dump every element of sequence [first, last) to std::cout
template<typename ForwardIt>
void dump_seq(ForwardIt first, ForwardIt last) {
  using ValueT = typename std::iterator_traits<ForwardIt>::value_type;
  std::copy(first, last,
      std::ostream_iterator<ValueT>{std::cout, " "});
  std::cout << std::endl;
}

// Checks wether ranges [first, last) and [ref_first, ref_last) are equal.
// If a mismatch is found, dumps elements that differ and returns true,
// otherwise false is returned.
template<typename ForwardIt, typename RefForwardIt, typename BinaryPredicateT>
bool check_fail_seq(ForwardIt first, ForwardIt last,
    RefForwardIt ref_first, RefForwardIt ref_last, BinaryPredicateT is_equal) {
  auto mism = std::mismatch(first, last, ref_first, is_equal);
  if (mism.first != last) {
    std::cout << "mismatch: returned " << *mism.first << std::endl;
    std::cout << "          expected " << *mism.second << std::endl;
    return true;
  }
  return false;
}

template<typename ForwardIt, typename RefForwardIt>
bool check_fail_seq(ForwardIt first, ForwardIt last,
    RefForwardIt ref_first, RefForwardIt ref_last) {
  return check_fail_seq(first, last, ref_first, ref_last,
      [] (const auto &lhs, const auto &rhs) { return lhs == rhs; });
}

// analog to C++20 bit_cast
template<typename To, typename From,
  typename std::enable_if<(sizeof(To) == sizeof(From)) &&
    std::is_trivially_copyable<From>::value &&
    std::is_trivial<To>::value, int>::type = 0>
To bit_cast(const From &src) noexcept
{
  To dst;
  std::memcpy(&dst, &src, sizeof(To));
  return dst;
}

static inline void *aligned_alloc(std::size_t alignment, std::size_t size) {
#ifdef _MSC_VER
  return _aligned_malloc(size, alignment);
#else
  return std::aligned_alloc(alignment, size);
#endif
}

static inline void aligned_free(void *ptr) {
#ifdef _MSC_VER
  _aligned_free(ptr);
#else
  std::free(ptr);
#endif
}

template<std::size_t width>
std::array<bool, width> unpack_mask(std::bitset<width> packed) {
  std::array<bool, width> unpacked;
  for (int i = 0; i != width; ++i)
    unpacked[i] = packed[i];
  return unpacked;
}

} // namespace cm_utils
