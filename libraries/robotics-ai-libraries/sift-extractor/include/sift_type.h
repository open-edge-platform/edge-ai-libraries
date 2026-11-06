/*
 * Copyright (C) 2026 Intel Corporation
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef SIFT_LZE_TYPE_H_
#define SIFT_LZE_TYPE_H_

class sift_lze_impl;

#ifdef OPENCV_FREE

#include <cstring>
#include <vector>

template <typename T = unsigned char, typename Container = std::vector<T>>
class mat {
public:
  mat() : cols(0), rows(0) {}

  mat(std::size_t height, std::size_t width) : cols(width), rows(height) {
    data_.assign(width * height, T{});
  }

  mat(std::size_t height, std::size_t width, T *in) : cols(width), rows(height) {
    data_.assign(in, in + width * height);
  }

  mat(std::size_t height, std::size_t width, T pattern) : cols(width), rows(height) {
    data_.assign(width * height, pattern);
  }

  std::size_t getWidth() const { return cols; }
  std::size_t getHeight() const { return rows; }
  bool empty() const { return cols == 0 || rows == 0; }

  void resize(std::size_t height, std::size_t width) {
    cols = width;
    rows = height;
    data_.assign(width * height, T{});
  }

  T *row(std::size_t cur_row) { return &data_[cur_row * cols]; }
  const T *row(std::size_t cur_row) const { return &data_[cur_row * cols]; }
  T *data() { return data_.data(); }
  const T *data() const { return data_.data(); }

  friend class sift_lze_impl;
  friend class sift_lze;

protected:
  std::size_t cols;
  std::size_t rows;
  Container data_;
};

typedef mat<unsigned char> Mat2d;
typedef mat<float> DescMat2d;
typedef Mat2d MatType;

struct KeyPoint {
  float x = 0.0f;
  float y = 0.0f;
  float size = 0.0f;
  float angle = -1.0f;
  float response = 0.0f;
  int octave = 0;

  KeyPoint() = default;
  KeyPoint(float x_, float y_, float size_, float angle_, float response_, int octave_)
      : x(x_), y(y_), size(size_), angle(angle_), response(response_), octave(octave_) {}
};

typedef KeyPoint KeyType;

#else // OPENCV_FREE

#include <opencv2/core/mat.hpp>
#include <opencv2/core/types.hpp>

typedef cv::Mat MatType;
typedef cv::KeyPoint KeyType;

#endif // OPENCV_FREE
#endif // SIFT_LZE_TYPE_H_
