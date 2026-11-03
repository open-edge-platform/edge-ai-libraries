/*
 * Copyright (C) 2026 Intel Corporation
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "sift_lze_impl.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <stdexcept>

#ifndef OPENCV_FREE
#include <opencv2/imgproc.hpp>
#endif

namespace {

sift_extractor::Backend parse_backend(const std::string &name) {
  const char *env = std::getenv("SIFT_BACKEND");
  const std::string effective = (env && *env) ? std::string(env) : name;
  return sift_extractor::backend_from_name(effective);
}

} // namespace

sift_lze_impl::sift_lze_impl(unsigned int max_num_keypts, unsigned int num_octaves,
                             float contrast_threshold, unsigned int no_of_cameras,
                             const std::string &backend,
                             const std::vector<std::vector<float>> &mask_rects)
    : max_num_keypts_(max_num_keypts), num_octaves_(num_octaves),
      contrast_threshold_(contrast_threshold), no_of_cameras_(no_of_cameras),
      backend_name_(backend), mask_rects_(mask_rects) {
  if (no_of_cameras_ == 0)
    throw std::invalid_argument("sift_lze: no_of_cameras must be >= 1");
  if (num_octaves_ == 0 || num_octaves_ > 8)
    throw std::invalid_argument("sift_lze: num_octaves out of range");
  (void)parse_backend(backend_name_);
}

sift_extractor::ExtractorOptions sift_lze_impl::make_options() const {
  sift_extractor::ExtractorOptions options;
#if SIFT_EXTRACTOR_HAS_OPENCL
  options.opencl.octaves = static_cast<int>(num_octaves_);
  options.opencl.contrast_threshold = contrast_threshold_;
  options.opencl.max_features = static_cast<int>(max_num_keypts_);
#endif
#if SIFT_EXTRACTOR_HAS_SYCL
  options.sycl.octaves = static_cast<int>(num_octaves_);
  options.sycl.contrast_threshold = contrast_threshold_;
  if (max_num_keypts_ > 0)
    options.sycl.capacity = std::max(options.sycl.capacity, static_cast<int>(max_num_keypts_) * 2);
#endif
  return options;
}

void sift_lze_impl::ensure_extractor(int width, int height) {
  if (extractor_ && width_ == width && height_ == height) return;
  width_ = width;
  height_ = height;
  const auto requested = parse_backend(backend_name_);
  extractor_ = std::make_unique<sift_extractor::Extractor>(width, height, requested, make_options());
  resolved_ = extractor_->backend();
}

std::vector<float> sift_lze_impl::to_float_gray(const unsigned char *u8, int width, int height,
                                                std::size_t step) const {
  std::vector<float> gray(static_cast<std::size_t>(width) * height);
  for (int y = 0; y < height; ++y) {
    const unsigned char *row = u8 + static_cast<std::size_t>(y) * step;
    float *out = gray.data() + static_cast<std::size_t>(y) * width;
    for (int x = 0; x < width; ++x) out[x] = static_cast<float>(row[x]);
  }
  return gray;
}

void sift_lze_impl::apply_rect_masks(std::vector<float> &gray, int width, int height) const {
  for (const auto &mask_rect : mask_rects_) {
    if (mask_rect.size() < 4) continue;
    const int x_min = std::clamp(static_cast<int>(std::lround((width / 4.0) * mask_rect[0])), 0, width);
    const int x_max = std::clamp(static_cast<int>(std::lround((width / 4.0) * mask_rect[1])), 0, width);
    const int y_min = std::clamp(static_cast<int>(std::lround((height / 4.0) * mask_rect[2])), 0, height);
    const int y_max = std::clamp(static_cast<int>(std::lround((height / 4.0) * mask_rect[3])), 0, height);
    for (int y = y_min; y < y_max; ++y) {
      float *row = gray.data() + static_cast<std::size_t>(y) * width;
      for (int x = x_min; x < x_max; ++x) row[x] = 0.0f;
    }
  }
}

void sift_lze_impl::apply_u8_mask(std::vector<float> &gray, const unsigned char *mask, int width,
                                  int height, std::size_t step) const {
  if (!mask) return;
  for (int y = 0; y < height; ++y) {
    const unsigned char *mrow = mask + static_cast<std::size_t>(y) * step;
    float *row = gray.data() + static_cast<std::size_t>(y) * width;
    for (int x = 0; x < width; ++x) {
      if (mrow[x] == 0) row[x] = 0.0f;
    }
  }
}

#ifdef OPENCV_FREE
void sift_lze_impl::extract(const std::vector<Mat2d> &in_image,
                            const std::vector<Mat2d> &in_image_mask,
                            std::vector<std::vector<KeyPoint>> &keypts,
                            std::vector<DescMat2d> &out_descriptors) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (in_image.empty() || in_image.size() > no_of_cameras_)
    throw std::invalid_argument("sift_lze: unexpected camera count");
  const int width = static_cast<int>(in_image[0].getWidth());
  const int height = static_cast<int>(in_image[0].getHeight());
  if (width <= 0 || height <= 0) throw std::invalid_argument("sift_lze: empty image");
  for (const auto &img : in_image) {
    if (static_cast<int>(img.getWidth()) != width || static_cast<int>(img.getHeight()) != height)
      throw std::invalid_argument("sift_lze: all images must share width/height");
  }
  ensure_extractor(width, height);
  keypts.assign(in_image.size(), std::vector<KeyPoint>{});
  out_descriptors.assign(in_image.size(), DescMat2d{});
  for (std::size_t cam = 0; cam < in_image.size(); ++cam) {
    auto gray = to_float_gray(in_image[cam].data(), width, height, static_cast<std::size_t>(width));
    apply_rect_masks(gray, width, height);
    if (cam < in_image_mask.size() && !in_image_mask[cam].empty()) {
      if (static_cast<int>(in_image_mask[cam].getWidth()) != width ||
          static_cast<int>(in_image_mask[cam].getHeight()) != height)
        throw std::invalid_argument("sift_lze: mask size mismatch");
      apply_u8_mask(gray, in_image_mask[cam].data(), width, height, static_cast<std::size_t>(width));
    }
    auto features = extractor_->extract(gray.data(), gray.size());
    if (max_num_keypts_ > 0 && features.size() > max_num_keypts_) {
      std::partial_sort(features.begin(), features.begin() + max_num_keypts_, features.end(),
                        [](const sift_extractor::SiftFeature &a, const sift_extractor::SiftFeature &b) {
                          return a.response > b.response;
                        });
      features.resize(max_num_keypts_);
    }
    auto &kps = keypts[cam];
    kps.resize(features.size());
    DescMat2d desc(features.size(), 128);
    for (std::size_t i = 0; i < features.size(); ++i) {
      const auto &f = features[i];
      kps[i] = KeyPoint(f.x, f.y, f.scale, f.orientation_degrees, f.response, 0);
      std::memcpy(desc.row(i), f.descriptor.data(), 128 * sizeof(float));
    }
    out_descriptors[cam] = std::move(desc);
  }
}
#else
void sift_lze_impl::extract(const cv::_InputArray &in_image, const cv::_InputArray &in_image_mask,
                            std::vector<std::vector<cv::KeyPoint>> &keypts,
                            const cv::_OutputArray &out_descriptors) {
  std::lock_guard<std::mutex> lock(mutex_);
  std::vector<cv::Mat> images;
  if (in_image.isMat()) {
    images.push_back(in_image.getMat());
  } else if (in_image.isMatVector()) {
    in_image.getMatVector(images);
  } else {
    cv::Mat single = in_image.getMat();
    if (!single.empty()) images.push_back(single);
  }
  if (images.empty()) throw std::invalid_argument("sift_lze: empty input");
  if (images.size() > no_of_cameras_)
    throw std::invalid_argument("sift_lze: unexpected camera count");

  std::vector<cv::Mat> masks;
  if (!in_image_mask.empty()) {
    if (in_image_mask.isMat()) {
      masks.push_back(in_image_mask.getMat());
    } else if (in_image_mask.isMatVector()) {
      in_image_mask.getMatVector(masks);
    } else {
      cv::Mat single = in_image_mask.getMat();
      if (!single.empty()) masks.push_back(single);
    }
  }

  cv::Mat gray0;
  if (images[0].channels() == 1)
    gray0 = images[0];
  else
    cv::cvtColor(images[0], gray0, cv::COLOR_BGR2GRAY);
  const int width = gray0.cols;
  const int height = gray0.rows;
  for (const auto &img : images) {
    if (img.cols != width || img.rows != height)
      throw std::invalid_argument("sift_lze: all images must share width/height");
  }
  ensure_extractor(width, height);

  keypts.assign(images.size(), std::vector<cv::KeyPoint>{});
  std::vector<cv::Mat> desc_mats(images.size());
  for (std::size_t cam = 0; cam < images.size(); ++cam) {
    cv::Mat gray;
    if (images[cam].channels() == 1)
      gray = images[cam];
    else
      cv::cvtColor(images[cam], gray, cv::COLOR_BGR2GRAY);
    if (!gray.isContinuous()) gray = gray.clone();
    auto pixels = to_float_gray(gray.ptr<unsigned char>(), width, height, gray.step1());
    apply_rect_masks(pixels, width, height);
    if (cam < masks.size() && !masks[cam].empty()) {
      cv::Mat mask = masks[cam];
      if (mask.type() != CV_8UC1) throw std::invalid_argument("sift_lze: mask must be CV_8UC1");
      if (mask.cols != width || mask.rows != height)
        throw std::invalid_argument("sift_lze: mask size mismatch");
      if (!mask.isContinuous()) mask = mask.clone();
      apply_u8_mask(pixels, mask.ptr<unsigned char>(), width, height, mask.step1());
    }
    auto features = extractor_->extract(pixels.data(), pixels.size());
    if (max_num_keypts_ > 0 && features.size() > max_num_keypts_) {
      std::partial_sort(features.begin(), features.begin() + max_num_keypts_, features.end(),
                        [](const sift_extractor::SiftFeature &a, const sift_extractor::SiftFeature &b) {
                          return a.response > b.response;
                        });
      features.resize(max_num_keypts_);
    }
    auto &kps = keypts[cam];
    kps.resize(features.size());
    cv::Mat desc(static_cast<int>(features.size()), 128, CV_32F);
    for (std::size_t i = 0; i < features.size(); ++i) {
      const auto &f = features[i];
      kps[i] = cv::KeyPoint(f.x, f.y, f.scale, f.orientation_degrees, f.response, 0);
      std::memcpy(desc.ptr<float>(static_cast<int>(i)), f.descriptor.data(), 128 * sizeof(float));
    }
    desc_mats[cam] = desc;
  }
    if (desc_mats.size() == 1 && out_descriptors.isMat()) {
    desc_mats[0].copyTo(out_descriptors);
  } else {
    out_descriptors.create(static_cast<int>(desc_mats.size()), 1, 0);
    out_descriptors.assign(desc_mats);
  }
}
#endif

sift_lze::sift_lze(unsigned int max_num_keypts, unsigned int num_octaves, float contrast_threshold,
                   unsigned int no_of_cameras, const std::string &backend,
                   const std::vector<std::vector<float>> &mask_rects)
    : extractor_impl(new sift_lze_impl(max_num_keypts, num_octaves, contrast_threshold, no_of_cameras,
                                       backend, mask_rects)) {}

sift_lze::~sift_lze() { delete extractor_impl; }

#ifdef OPENCV_FREE
void sift_lze::extract(const std::vector<Mat2d> &in_image, const std::vector<Mat2d> &in_image_mask,
                       std::vector<std::vector<KeyPoint>> &keypts,
                       std::vector<DescMat2d> &out_descriptors) {
  extractor_impl->extract(in_image, in_image_mask, keypts, out_descriptors);
}
#else
void sift_lze::extract(const cv::_InputArray &in_image, const cv::_InputArray &in_image_mask,
                       std::vector<std::vector<cv::KeyPoint>> &keypts,
                       const cv::_OutputArray &out_descriptors) {
  extractor_impl->extract(in_image, in_image_mask, keypts, out_descriptors);
}
#endif

unsigned int sift_lze::get_max_num_keypoints() const { return extractor_impl->max_num_keypts_; }
void sift_lze::set_max_num_keypoints(unsigned int max_num_keypts) {
  std::lock_guard<std::mutex> lock(extractor_impl->mutex_);
  extractor_impl->max_num_keypts_ = max_num_keypts;
  extractor_impl->extractor_.reset();
}

unsigned int sift_lze::get_num_octaves() const { return extractor_impl->num_octaves_; }
void sift_lze::set_num_octaves(unsigned int num_octaves) {
  std::lock_guard<std::mutex> lock(extractor_impl->mutex_);
  extractor_impl->num_octaves_ = num_octaves;
  extractor_impl->extractor_.reset();
}

float sift_lze::get_contrast_threshold() const { return extractor_impl->contrast_threshold_; }
void sift_lze::set_contrast_threshold(float contrast_threshold) {
  std::lock_guard<std::mutex> lock(extractor_impl->mutex_);
  extractor_impl->contrast_threshold_ = contrast_threshold;
  extractor_impl->extractor_.reset();
}

std::string sift_lze::get_backend() const { return extractor_impl->backend_name_; }
void sift_lze::set_backend(const std::string &backend) {
  std::lock_guard<std::mutex> lock(extractor_impl->mutex_);
  (void)parse_backend(backend);
  extractor_impl->backend_name_ = backend;
  extractor_impl->extractor_.reset();
}

std::string sift_lze::get_resolved_backend() const {
  std::lock_guard<std::mutex> lock(extractor_impl->mutex_);
  if (!extractor_impl->extractor_) return "";
  return sift_extractor::backend_name(extractor_impl->resolved_);
}
