#include "opencl_extrema.hpp"

#include <opencv2/core.hpp>
#include <opencv2/core/ocl.hpp>
#include <opencv2/features2d.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {

struct FeatureSet {
  std::vector<cv::Point2f> positions;
  cv::Mat descriptors;
};

FeatureSet extract_opencl(sift_extractor::detail::OpenCLDoGExtrema &extractor,
                          const cv::Mat &gray) {
  std::vector<float> pixels(static_cast<size_t>(gray.rows) * gray.cols);
  for (int row = 0; row < gray.rows; ++row) {
    for (int column = 0; column < gray.cols; ++column)
      pixels[static_cast<size_t>(row) * gray.cols + column] =
          static_cast<float>(gray.at<unsigned char>(row, column));
  }
  const auto features = extractor.extract_image(pixels, gray.cols, gray.rows,
                                                 4, 3, 1.6f, 1.0f, 12.1f);
  FeatureSet result;
  result.descriptors.create(static_cast<int>(features.size()), 128, CV_32F);
  for (size_t index = 0; index < features.size(); ++index) {
    result.positions.emplace_back(features[index].point.keypoint.image_x,
                                   features[index].point.keypoint.image_y);
    std::copy(features[index].descriptor.begin(), features[index].descriptor.end(),
               result.descriptors.ptr<float>(static_cast<int>(index)));
  }
  return result;
}

FeatureSet extract_opencv(const cv::Mat &gray) {
  const auto sift = cv::SIFT::create();
  std::vector<cv::KeyPoint> keypoints;
  FeatureSet result;
  sift->detectAndCompute(gray, cv::noArray(), keypoints, result.descriptors);
  for (const auto &point : keypoints) result.positions.push_back(point.pt);
  return result;
}

void report(cv::FileStorage &output, const char *name, const FeatureSet &first,
            const FeatureSet &second, const cv::Mat &affine) {
  int accepted = 0;
  int inliers = 0;
  double squared_error_sum = 0.0;
  if (!first.descriptors.empty() && second.descriptors.rows >= 2) {
    std::vector<std::vector<cv::DMatch>> neighbors;
    cv::BFMatcher(cv::NORM_L2).knnMatch(first.descriptors, second.descriptors,
                                       neighbors, 2);
    for (const auto &pair : neighbors) {
      if (pair.size() < 2 || pair[0].distance >= 0.8f * pair[1].distance) continue;
      ++accepted;
      const auto &source = first.positions[static_cast<size_t>(pair[0].queryIdx)];
      const auto &target = second.positions[static_cast<size_t>(pair[0].trainIdx)];
      const double projected_x = affine.at<double>(0, 0) * source.x +
                                  affine.at<double>(0, 1) * source.y + affine.at<double>(0, 2);
      const double projected_y = affine.at<double>(1, 0) * source.x +
                                  affine.at<double>(1, 1) * source.y + affine.at<double>(1, 2);
      const double error_x = target.x - projected_x;
      const double error_y = target.y - projected_y;
      const double squared_error = error_x * error_x + error_y * error_y;
      if (squared_error <= 9.0) {
        ++inliers;
        squared_error_sum += squared_error;
      }
    }
  }
  output << name << "{" << "first_features" << static_cast<int>(first.positions.size())
         << "second_features" << static_cast<int>(second.positions.size())
         << "ratio_matches" << accepted << "ground_truth_inliers_3px" << inliers
         << "inlier_fraction" << (accepted ? static_cast<double>(inliers) / accepted : 0.0)
         << "inlier_rmse_px" << (inliers ? std::sqrt(squared_error_sum / inliers) : -1.0)
         << "}";
}

} // namespace

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "Usage: validate_sift_pair <grayscale-or-color-image>\n";
    return 2;
  }
  try {
    cv::ocl::setUseOpenCL(false);
    cv::Mat first = cv::imread(argv[1], cv::IMREAD_GRAYSCALE);
    if (first.empty()) throw std::runtime_error("Cannot read input image");
    if (first.cols > 640 || first.rows > 480) {
      const double factor = std::min(640.0 / first.cols, 480.0 / first.rows);
      cv::resize(first, first, cv::Size(), factor, factor, cv::INTER_AREA);
    }
    const cv::Mat affine = cv::getRotationMatrix2D(
        cv::Point2f((first.cols - 1) * 0.5f, (first.rows - 1) * 0.5f), 30.0, 0.85);
    cv::Mat second;
    cv::warpAffine(first, second, affine, first.size(), cv::INTER_LINEAR,
                     cv::BORDER_CONSTANT);
    sift_extractor::detail::OpenCLDoGExtrema extractor;
    const auto first_opencl = extract_opencl(extractor, first);
    const auto second_opencl = extract_opencl(extractor, second);
    const auto first_opencv = extract_opencv(first);
    const auto second_opencv = extract_opencv(second);
    cv::FileStorage output(".json", cv::FileStorage::WRITE |
        cv::FileStorage::MEMORY | cv::FileStorage::FORMAT_JSON);
    output << "diagnostic_only" << 1 << "cuda_reference_available" << 0
           << "performance_measured" << 0 << "parameters_equivalent" << 0
           << "input" << argv[1] << "width" << first.cols << "height" << first.rows
          << "rotation_degrees" << 30.0 << "scale_factor" << 0.85
          << "prototype_octaves" << 4 << "prototype_intervals" << 3
          << "prototype_base_sigma" << 1.6 << "prototype_contrast" << 1.0
          << "prototype_hessian_ratio_limit" << 12.1
          << "reference" << "OpenCV CPU SIFT defaults"
          << "reference_opencv_version" << CV_VERSION
          << "ratio_threshold" << 0.8 << "inlier_threshold_px" << 3.0;
    report(output, "opencl_prototype", first_opencl, second_opencl, affine);
    report(output, "opencv_cpu_default", first_opencv, second_opencv, affine);
    std::cout << output.releaseAndGetString() << '\n';
  } catch (const std::exception &error) {
    std::cerr << "Validation failed: " << error.what() << '\n';
    return 1;
  }
  return 0;
}