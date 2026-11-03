// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "sift_extractor/extractor.hpp"

#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

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
  // Release the GIL during native extraction; NumPy buffer must remain alive.
  py::gil_scoped_release release;
  return extractor.extract(pixels, count, static_cast<std::size_t>(width));
}

} // namespace

PYBIND11_MODULE(sift_extractor, module) {
  using sift_extractor::Backend;
  using sift_extractor::Extractor;
  using sift_extractor::ExtractorOptions;
  using sift_extractor::available_backends;
  using sift_extractor::backend_name;
  using sift_extractor::backend_from_name;
  using sift_extractor::resolve_backend;

  module.doc() =
      "Intel SIFT extractor Python bindings (dual OpenCL/SYCL dispatch; "
      "compare against OpenCV; not quality-certified).";

  module.attr("__version__") = SIFT_EXTRACTOR_VERSION_STRING;

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
}
