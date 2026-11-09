// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/optical_flow.hpp"

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

optical_flow_sdk::ImageView numpy_to_image(const py::array &arr) {
  if (arr.ndim() != 2)
    throw std::invalid_argument("image must be a 2-D HxW array");
  auto buf = arr.request();
  if (buf.itemsize != 1)
    throw std::invalid_argument("image dtype must be uint8");
  return optical_flow_sdk::ImageView{
      static_cast<const std::uint8_t *>(buf.ptr), static_cast<int>(buf.shape[1]),
      static_cast<int>(buf.shape[0]), static_cast<std::size_t>(buf.strides[0])};
}

py::array_t<float> flow_to_numpy(const optical_flow_sdk::FlowField &flow) {
  py::array_t<float> out({flow.height, flow.width, 2});
  auto buf = out.mutable_unchecked<3>();
  for (int y = 0; y < flow.height; ++y) {
    for (int x = 0; x < flow.width; ++x) {
      buf(y, x, 0) = flow.dx(x, y);
      buf(y, x, 1) = flow.dy(x, y);
    }
  }
  return out;
}

py::array_t<std::uint8_t> cost_to_numpy(const optical_flow_sdk::CostMap &cost) {
  py::array_t<std::uint8_t> out({cost.height, cost.width});
  auto buf = out.mutable_unchecked<2>();
  for (int y = 0; y < cost.height; ++y) {
    for (int x = 0; x < cost.width; ++x)
      buf(y, x) = cost.at(x, y);
  }
  return out;
}

} // namespace

PYBIND11_MODULE(_native, module) {
  module.doc() = "Intel Optical Flow SDK Python bindings";

  py::enum_<optical_flow_sdk::Backend>(module, "Backend")
      .value("Auto", optical_flow_sdk::Backend::Auto)
      .value("Cpu", optical_flow_sdk::Backend::Cpu)
      .value("OpenCL", optical_flow_sdk::Backend::OpenCL)
      .value("Sycl", optical_flow_sdk::Backend::Sycl);

  py::enum_<optical_flow_sdk::Preset>(module, "Preset")
      .value("Slow", optical_flow_sdk::Preset::Slow)
      .value("Medium", optical_flow_sdk::Preset::Medium)
      .value("Fast", optical_flow_sdk::Preset::Fast);

  py::enum_<optical_flow_sdk::Algorithm>(module, "Algorithm")
      .value("Dis", optical_flow_sdk::Algorithm::Dis)
      .value("Farneback", optical_flow_sdk::Algorithm::Farneback);

  module.def("backend_name", &optical_flow_sdk::backend_name);
  module.def("preset_name", &optical_flow_sdk::preset_name);
  module.def("algorithm_name", &optical_flow_sdk::algorithm_name);
  module.def("available_backends", []() {
    std::vector<std::string> names;
    for (auto b : optical_flow_sdk::available_backends())
      names.emplace_back(optical_flow_sdk::backend_name(b));
    return names;
  });
  module.def("resolve_backend", [](const std::string &name) {
    return optical_flow_sdk::backend_name(
        optical_flow_sdk::resolve_backend(optical_flow_sdk::backend_from_name(name)));
  });

  py::class_<optical_flow_sdk::OpticalFlow>(module, "OpticalFlow")
      .def(py::init([](const std::string &backend, const std::string &preset,
                       const std::string &algorithm) {
             return std::make_unique<optical_flow_sdk::OpticalFlow>(
                 optical_flow_sdk::backend_from_name(backend),
                 optical_flow_sdk::preset_from_name(preset),
                 optical_flow_sdk::algorithm_from_name(algorithm));
           }),
           py::arg("backend") = "auto", py::arg("preset") = "fast",
           py::arg("algorithm") = "dis")
      .def_property_readonly("backend",
                             [](const optical_flow_sdk::OpticalFlow &self) {
                               return optical_flow_sdk::backend_name(self.backend());
                             })
      .def_property_readonly("preset",
                             [](const optical_flow_sdk::OpticalFlow &self) {
                               return optical_flow_sdk::preset_name(self.preset());
                             })
      .def_property_readonly("algorithm",
                             [](const optical_flow_sdk::OpticalFlow &self) {
                               return optical_flow_sdk::algorithm_name(self.algorithm());
                             })
      .def(
          "calc",
          [](optical_flow_sdk::OpticalFlow &self, const py::array &prev, const py::array &next,
             bool with_cost) {
            optical_flow_sdk::FlowField flow;
            if (with_cost) {
              optical_flow_sdk::CostMap cost;
              self.calc(numpy_to_image(prev), numpy_to_image(next), flow, cost);
              return py::make_tuple(flow_to_numpy(flow), cost_to_numpy(cost));
            }
            self.calc(numpy_to_image(prev), numpy_to_image(next), flow);
            return py::make_tuple(flow_to_numpy(flow), py::none());
          },
          py::arg("prev"), py::arg("next"), py::arg("with_cost") = false)
      .def(
          "calc_both",
          [](optical_flow_sdk::OpticalFlow &self, const py::array &prev, const py::array &next) {
            optical_flow_sdk::FlowField fwd;
            optical_flow_sdk::FlowField bwd;
            self.calcBoth(numpy_to_image(prev), numpy_to_image(next), fwd, bwd);
            return py::make_tuple(flow_to_numpy(fwd), flow_to_numpy(bwd));
          },
          py::arg("prev"), py::arg("next"));
}
