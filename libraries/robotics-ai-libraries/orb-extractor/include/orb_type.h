// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __ORB_TYPE_H__
#define __ORB_TYPE_H__

class orb_extractor_impl;

#ifdef OPENCV_FREE

#include <cstring>
#include <string>
#include <vector>

template <typename T = unsigned char,
         typename Container = std::vector<T>>
class mat {

public:

 ~mat() { };
  mat() { cols = 0; rows = 0; }

  mat(std::size_t height, std::size_t width)
  {
    cols = width;
    rows = height;
    data_.clear();
    data_.resize(width*height*sizeof(T));
  }


  mat(std::size_t height, std::size_t width, T *in)
  {
    cols = width;
    rows = height;
    data_ = std::vector<T>(in, in + width * height * sizeof(T));
  }

  mat(std::size_t height, std::size_t width, T pattern)
  {
    cols = width;
    rows = height;
    data_.resize(width*height*sizeof(T));

    std::memset(data_.data(), pattern, data_.size());
  }

  const std::size_t getWidth() const { return cols; }
  const std::size_t getHeight() const { return rows; }
  const std::size_t getSize() const { return data_.size(); }

  const bool empty() const { return ((cols == 0) && (rows == 0)) ? true : false; }

  void resize(size_t height, size_t width)
  {
    cols = width;
    rows = height;
    data_.resize(width*height*sizeof(T));
  }

  T* row(size_t cur_row) { return &data_[cur_row*cols]; }

  T* data() { return data_.data(); }
  const T* data() const { return data_.data(); }

  template<typename CT>
  CT* ptr(size_t row, size_t col) { return &data_[row*cols + col];  }

  template<typename CT>
  const CT* ptr(size_t row, size_t col) const { return &data_[row*cols + col]; }

  friend class orb_extractor_impl;
  friend class orb_extractor;

  T type() { return sizeof(T); }

protected:
  std::size_t cols;
  std::size_t rows;
  Container   data_;
};


typedef mat<unsigned char> Mat2d;
typedef Mat2d MatType;

template <typename T = unsigned char,
         typename Container = std::vector<T>>
class MatArray {
public:

  virtual ~MatArray() {}
  MatArray() {}

  MatArray(std::vector<Mat2d> &vec) { vec2d = vec; }

  std::vector<Mat2d> getMatVector() { return vec2d; }

protected:
  std::vector<Mat2d>& vec2d;
};




struct KeyPoint {

  /// 2D location of the feature point on the image in pixel coordinates.
  float x, y;
  /// Diameter of the meaningful keypoint neighbourhood.
  float size;
  /// Orientation of the feature point.
  float angle;
  /// Strength of the keypoint.
  float response;
  /// Index of the pyramid level the keypoint was found in.
  int octave;

  KeyPoint() : x(0.0f), y(0.0f), size(0.0f), angle(-1.0f),
    response(0.0f), octave(0) {};
  KeyPoint(float x, float y, float size, float angle, float response, int octave)
    : x(x), y(y), size(size), angle(angle), response(response), octave(octave)  {};

  KeyPoint(float x, float y, float size, float angle, float response)
    : KeyPoint(x, y, size, angle, response, 0) {};

  KeyPoint(float x, float y, float size) : KeyPoint(x, y, size, -1.0f, 0.0f, 0) {};
};

typedef KeyPoint KeyType;


#else

#include <opencv2/core/mat.hpp>
#include <opencv2/core/types.hpp>

typedef cv::Mat MatType;
typedef cv::KeyPoint KeyType;

#endif
#endif // __ORB_TYPE_H_
