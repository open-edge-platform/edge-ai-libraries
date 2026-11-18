// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "sift_extractor/opencv_adapter.hpp"

#include <stdexcept>

namespace sift_extractor::opencv {

cv::KeyPoint to_keypoint(const SiftFeature &feature) {
  cv::KeyPoint point;
  point.pt.x = feature.x;
  point.pt.y = feature.y;
  point.size = 2.0f * feature.scale;
  point.angle = feature.orientation_degrees;
  point.response = feature.response;
  point.octave = 0;
  point.class_id = -1;
  return point;
}

void to_opencv(const std::vector<SiftFeature> &features,
               std::vector<cv::KeyPoint> &keypoints, cv::Mat &descriptors) {
  keypoints.clear();
  keypoints.reserve(features.size());
  descriptors.create(static_cast<int>(features.size()), 128, CV_32F);
  for (std::size_t index = 0; index < features.size(); ++index) {
    const auto &feature = features[index];
    keypoints.push_back(to_keypoint(feature));
    float *row = descriptors.ptr<float>(static_cast<int>(index));
    for (int bin = 0; bin < 128; ++bin) row[bin] = feature.descriptor[static_cast<std::size_t>(bin)];
  }
}

cv::Mat to_float_gray(const cv::Mat &image) {
  if (image.empty()) throw std::invalid_argument("OpenCV adapter image is empty");
  if (image.channels() != 1)
    throw std::invalid_argument("OpenCV adapter requires single-channel grayscale");

  cv::Mat float_image;
  if (image.type() == CV_32FC1) {
    float_image = image.isContinuous() ? image : image.clone();
  } else if (image.type() == CV_8UC1) {
    image.convertTo(float_image, CV_32F);
  } else {
    throw std::invalid_argument("OpenCV adapter accepts CV_8UC1 or CV_32FC1 only");
  }
  if (!float_image.isContinuous()) float_image = float_image.clone();
  return float_image;
}

std::vector<SiftFeature> extract(Extractor &extractor, const cv::Mat &image) {
  const cv::Mat pixels = to_float_gray(image);
  if (pixels.cols != extractor.width() || pixels.rows != extractor.height())
    throw std::invalid_argument("OpenCV adapter image shape must match extractor width/height");
  const auto count = static_cast<std::size_t>(pixels.cols) * static_cast<std::size_t>(pixels.rows);
  return extractor.extract(pixels.ptr<float>(), count, static_cast<std::size_t>(pixels.cols));
}

void detect_and_compute(Extractor &extractor, const cv::Mat &image,
                        std::vector<cv::KeyPoint> &keypoints, cv::Mat &descriptors) {
  to_opencv(extract(extractor, image), keypoints, descriptors);
}

} // namespace sift_extractor::opencv
