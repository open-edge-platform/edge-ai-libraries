# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Create single axis demo executable
add_executable(multi-axis-monitor multi-axis-monitor.cpp)
target_link_libraries(multi-axis-monitor
  rtm_algo_com
  rtm_algo_pub
  rtm_fb_com
  rtm_fb_pub
  -lpthread
)

add_executable(multi-axis multi-axis.cpp)
target_link_libraries(multi-axis
  rtm_algo_com
  rtm_algo_pub
  rtm_fb_com
  rtm_fb_pub
  -lpthread
)

if (TCC)
  add_executable(multi-axis-tcc-measure multi-axis-tcc-measure.cpp)
  target_link_libraries(multi-axis-tcc-measure
    rtm_algo_com
    rtm_algo_pub
    rtm_fb_com
    rtm_fb_pub
    ${ITT_LIBRARIES} 
    ${TCC_LIBRARIES}
    ${TCC_CACHE_LIBRARIES}
    ${TCC_STATIC_LIBRARIES}
    ruckig::ruckig
    -lpthread
    -ldl
  )

  add_executable(multi-axis-tcc-ssram multi-axis-tcc-ssram.cpp)
  target_link_libraries(multi-axis-tcc-ssram 
    rtm_algo_com
    rtm_algo_pub
    rtm_fb_com
    rtm_fb_pub
    ${ITT_LIBRARIES} 
    ${TCC_LIBRARIES}
    ${TCC_CACHE_LIBRARIES}
    ${TCC_STATIC_LIBRARIES}
    ruckig::ruckig
    -lpthread
    -ldl
  )

  install(
    TARGETS multi-axis-tcc-measure multi-axis-tcc-ssram
    DESTINATION ${INSTALL_BINDIR}
  )
endif(TCC)

install(
  TARGETS multi-axis multi-axis-monitor
  DESTINATION ${INSTALL_BINDIR}
)
