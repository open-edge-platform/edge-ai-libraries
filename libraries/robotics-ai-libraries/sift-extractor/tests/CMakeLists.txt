# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

add_executable(test_sift_lze_ocvfree test_ocvfree.cpp)
target_link_libraries(test_sift_lze_ocvfree PRIVATE sift_lze_ocvfree)
add_test(NAME test_sift_lze_ocvfree COMMAND test_sift_lze_ocvfree)

if(ENABLE_OPENCV)
  add_executable(test_sift_lze_opencv test_opencv.cpp)
  target_link_libraries(test_sift_lze_opencv PRIVATE sift_lze ${OpenCV_LIBS})
  add_test(NAME test_sift_lze_opencv COMMAND test_sift_lze_opencv)

  add_executable(test_sift_lze_same_core test_same_core.cpp)
  target_link_libraries(test_sift_lze_same_core PRIVATE sift_lze sift_extractor::sift_extractor
                                                        ${OpenCV_LIBS})
  add_test(NAME test_sift_lze_same_core COMMAND test_sift_lze_same_core)
endif()
