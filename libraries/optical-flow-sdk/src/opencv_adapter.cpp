// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/opencv_adapter.hpp"

#include <stdexcept>
#include <string>

namespace optical_flow_sdk::opencv {

namespace {

cv::Mat require_gray8(const cv::Mat &image, const char *name) {
  if (image.empty())
    throw std::invalid_argument(std::string(name) + " is empty");
  if (image.type() != CV_8UC1)
    throw std::invalid_argument(std::string(name) + " must be CV_8UC1 grayscale");
  return image.isContinuous() ? image : image.clone();
}

} // namespace

ImageView as_image_view(const cv::Mat &gray8) {
  const cv::Mat img = require_gray8(gray8, "image");
  return ImageView{img.ptr<std::uint8_t>(), img.cols, img.rows,
                   static_cast<std::size_t>(img.step)};
}

cv::Mat to_mat(const FlowField &flow) {
  cv::Mat out(flow.height, flow.width, CV_32FC2);
  for (int y = 0; y < flow.height; ++y) {
    auto *row = out.ptr<cv::Vec2f>(y);
    for (int x = 0; x < flow.width; ++x)
      row[x] = cv::Vec2f(flow.dx(x, y), flow.dy(x, y));
  }
  return out;
}

cv::Mat to_mat(const CostMap &cost) {
  cv::Mat out(cost.height, cost.width, CV_8UC1);
  for (int y = 0; y < cost.height; ++y) {
    auto *row = out.ptr<std::uint8_t>(y);
    for (int x = 0; x < cost.width; ++x)
      row[x] = cost.at(x, y);
  }
  return out;
}

FlowField to_flow_field(const cv::Mat &flow32fc2) {
  if (flow32fc2.type() != CV_32FC2)
    throw std::invalid_argument("flow must be CV_32FC2");
  FlowField flow;
  flow.allocate(flow32fc2.cols, flow32fc2.rows);
  for (int y = 0; y < flow32fc2.rows; ++y) {
    const auto *row = flow32fc2.ptr<cv::Vec2f>(y);
    for (int x = 0; x < flow32fc2.cols; ++x) {
      flow.dx(x, y) = row[x][0];
      flow.dy(x, y) = row[x][1];
    }
  }
  return flow;
}

void calc(OpticalFlow &of, const cv::Mat &prev_gray8, const cv::Mat &next_gray8,
          cv::Mat &flow32fc2) {
  FlowField flow;
  of.calc(as_image_view(prev_gray8), as_image_view(next_gray8), flow);
  flow32fc2 = to_mat(flow);
}

void calc(OpticalFlow &of, const cv::Mat &prev_gray8, const cv::Mat &next_gray8,
          cv::Mat &flow32fc2, cv::Mat &cost8u) {
  FlowField flow;
  CostMap cost;
  of.calc(as_image_view(prev_gray8), as_image_view(next_gray8), flow, cost);
  flow32fc2 = to_mat(flow);
  cost8u = to_mat(cost);
}

} // namespace optical_flow_sdk::opencv
