# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

add_executable(sift_feature_extract main.cpp)
target_link_libraries(sift_feature_extract PRIVATE sift_lze ${OpenCV_LIBS})
install(TARGETS sift_feature_extract RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES main.cpp CMakeLists.txt tutorial.md
  DESTINATION opt/intel/sift_lze/samples)
