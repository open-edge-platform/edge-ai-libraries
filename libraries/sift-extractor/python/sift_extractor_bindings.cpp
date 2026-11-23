// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "sift_extractor/extractor.hpp"
#include "sift_extractor/version.hpp"

#if SIFT_EXTRACTOR_HAS_OPENCL
#include "sift_extractor/opencl_matcher.hpp"
#endif

#include <algorithm>
#include <cmath>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

#if SIFT_EXTRACTOR_HAS_OPENCL
using MatchResult = sift_extractor::SiftMatchResult;
#else
struct MatchResult {
  int match = -1;
  float score = 0.0f;
  float ambiguity = 1.0f;
  float match_x = 0.0f;
  float match_y = 0.0f;
};
#endif

py::dict feature_to_dict(const sift_extractor::SiftFeature &feature) {
  py::dict item;
  item["x"] = feature.x;
  item["y"] = feature.y;
  item["scale"] = feature.scale;
  item["orientation_degrees"] = feature.orientation_degrees;
  item["response"] = feature.response;
  py::array_t<float> descriptor(128);
  std::memcpy(descriptor.mutable_data(), feature.descriptor.data(), 128 * sizeof(float));
  item["descriptor"] = descriptor;
  return item;
}

sift_extractor::SiftFeature dict_to_feature(const py::handle &handle) {
  py::dict item = py::reinterpret_borrow<py::dict>(handle);
  sift_extractor::SiftFeature feature;
  feature.x = item["x"].cast<float>();
  feature.y = item["y"].cast<float>();
  if (item.contains("scale")) feature.scale = item["scale"].cast<float>();
  if (item.contains("orientation_degrees"))
    feature.orientation_degrees = item["orientation_degrees"].cast<float>();
  if (item.contains("response")) feature.response = item["response"].cast<float>();
  auto descriptor = py::array_t<float, py::array::c_style | py::array::forcecast>::ensure(
      item["descriptor"]);
  if (!descriptor || descriptor.ndim() != 1 || descriptor.shape(0) != 128)
    throw std::invalid_argument("feature descriptor must be a length-128 float array");
  std::memcpy(feature.descriptor.data(), descriptor.data(), 128 * sizeof(float));
  return feature;
}

std::vector<sift_extractor::SiftFeature> list_to_features(const py::sequence &features) {
  std::vector<sift_extractor::SiftFeature> out;
  out.reserve(py::len(features));
  for (const auto &item : features) out.push_back(dict_to_feature(item));
  return out;
}

py::dict match_to_dict(std::size_t query_index, const MatchResult &match) {
  py::dict item;
  item["query_index"] = static_cast<int>(query_index);
  item["train_index"] = match.match;
  item["score"] = match.score;
  item["ambiguity"] = match.ambiguity;
  item["match_x"] = match.match_x;
  item["match_y"] = match.match_y;
  return item;
}

std::vector<sift_extractor::SiftFeature> extract_numpy(
    sift_extractor::Extractor &extractor,
    py::array_t<float, py::array::c_style | py::array::forcecast> image) {
  if (image.ndim() != 2)
    throw std::invalid_argument("image must be a 2-D float32 array (H, W)");
  const auto height = static_cast<int>(image.shape(0));
  const auto width = static_cast<int>(image.shape(1));
  if (width != extractor.width() || height != extractor.height())
    throw std::invalid_argument("image shape must match extractor width/height");
  const auto *pixels = image.data();
  const auto count = static_cast<std::size_t>(width) * static_cast<std::size_t>(height);
  py::gil_scoped_release release;
  return extractor.extract(pixels, count, static_cast<std::size_t>(width));
}

// Host matcher matching OpenCL/SYCL convention: score = descriptor dot product
// (higher better); ambiguity = second_best / (best + eps). Lowe: ambiguity < ratio.
std::vector<MatchResult> match_features_host(
    const std::vector<sift_extractor::SiftFeature> &query,
    const std::vector<sift_extractor::SiftFeature> &train) {
  std::vector<MatchResult> results(query.size());
  if (train.empty()) return results;
  for (std::size_t qi = 0; qi < query.size(); ++qi) {
    float best = -1.0f;
    float second = -1.0f;
    int best_index = -1;
    for (std::size_t ti = 0; ti < train.size(); ++ti) {
      float dot = 0.0f;
      for (int d = 0; d < 128; ++d) {
        dot += query[qi].descriptor[static_cast<std::size_t>(d)] *
               train[ti].descriptor[static_cast<std::size_t>(d)];
      }
      if (dot > best) {
        second = best;
        best = dot;
        best_index = static_cast<int>(ti);
      } else if (dot > second) {
        second = dot;
      }
    }
    auto &out = results[qi];
    out.match = best_index;
    out.score = best;
    out.ambiguity = (second >= 0.0f) ? second / (best + 1.0e-6f) : 1.0f;
    if (best_index >= 0) {
      out.match_x = train[static_cast<std::size_t>(best_index)].x;
      out.match_y = train[static_cast<std::size_t>(best_index)].y;
    }
  }
  return results;
}

py::list filter_matches(const std::vector<MatchResult> &raw, float ratio) {
  py::list accepted;
  for (std::size_t i = 0; i < raw.size(); ++i) {
    const auto &match = raw[i];
    if (match.match < 0) continue;
    // OpenCL matcher stores ambiguity = second/(best+eps); accept when < ratio.
    // Host path uses the same convention on squared distances.
    if (!(match.ambiguity < ratio)) continue;
    accepted.append(match_to_dict(i, match));
  }
  return accepted;
}

} // namespace

PYBIND11_MODULE(_native, module) {
  using sift_extractor::Backend;
  using sift_extractor::Extractor;
  using sift_extractor::ExtractorOptions;
  using sift_extractor::available_backends;
  using sift_extractor::backend_name;
  using sift_extractor::backend_from_name;
  using sift_extractor::resolve_backend;

  module.doc() =
      "Intel SIFT extractor/matcher Python bindings (OpenCL/SYCL extract; "
      "OpenCL GPU match or host L2 fallback). Not quality-certified.";

  module.attr("__version__") = SIFT_EXTRACTOR_VERSION_STRING;
  module.attr("has_opencl_matcher") = static_cast<bool>(SIFT_EXTRACTOR_HAS_OPENCL);

  py::enum_<Backend>(module, "Backend")
      .value("Auto", Backend::Auto)
      .value("OpenCL", Backend::OpenCL)
      .value("Sycl", Backend::Sycl);

  module.def("available_backends", []() {
    py::list names;
    for (auto backend : available_backends()) names.append(backend_name(backend));
    return names;
  });
  module.def("resolve_backend", [](const std::string &name) {
    return std::string(backend_name(resolve_backend(backend_from_name(name))));
  });

  py::class_<Extractor>(module, "Extractor")
      .def(py::init([](int width, int height, const std::string &backend) {
             return std::make_unique<Extractor>(width, height, backend_from_name(backend),
                                                ExtractorOptions{});
           }),
           py::arg("width"), py::arg("height"), py::arg("backend") = "auto")
      .def_property_readonly("backend",
                             [](const Extractor &self) { return backend_name(self.backend()); })
      .def_property_readonly("width", &Extractor::width)
      .def_property_readonly("height", &Extractor::height)
      .def(
          "extract",
          [](Extractor &self, py::array_t<float, py::array::c_style | py::array::forcecast> image) {
            const auto features = extract_numpy(self, image);
            py::list out;
            for (const auto &feature : features) out.append(feature_to_dict(feature));
            return out;
          },
          py::arg("image"),
          "Extract SIFT features from a contiguous float32 HxW grayscale image.");

#if SIFT_EXTRACTOR_HAS_OPENCL
  py::class_<sift_extractor::OpenCLMatcher>(module, "OpenCLMatcher")
      .def(py::init<>())
      .def(
          "match",
          [](sift_extractor::OpenCLMatcher &self, const py::sequence &query,
             const py::sequence &train, float ratio) {
            const auto q = list_to_features(query);
            const auto t = list_to_features(train);
            std::vector<MatchResult> raw;
            {
              py::gil_scoped_release release;
              raw = self.match(q, t);
            }
            return filter_matches(raw, ratio);
          },
          py::arg("query"), py::arg("train"), py::arg("ratio") = 0.8f,
          "GPU match query→train features; returns Lowe-ratio survivors "
          "(ambiguity < ratio).");
#endif

  module.def(
      "match",
      [](const py::sequence &query, const py::sequence &train, float ratio) {
        const auto q = list_to_features(query);
        const auto t = list_to_features(train);
        std::vector<MatchResult> raw;
        {
          py::gil_scoped_release release;
#if SIFT_EXTRACTOR_HAS_OPENCL
          sift_extractor::OpenCLMatcher matcher;
          raw = matcher.match(q, t);
#else
          raw = match_features_host(q, t);
#endif
        }
        return filter_matches(raw, ratio);
      },
      py::arg("query"), py::arg("train"), py::arg("ratio") = 0.8f,
      "Match descriptors (OpenCL GPU matcher when built; else host L2). "
      "Returns list of dicts passing Lowe ratio (ambiguity < ratio).");
}
