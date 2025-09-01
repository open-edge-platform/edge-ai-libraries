# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
# Set default install directories
SET(CMAKE_INSTALL_INCLUDEDIR include)
SET(CMAKE_INSTALL_LIBDIR lib)
SET(CMAKE_INSTALL_BINDIR bin)

# INSTALL_BINDIR is used at command line to define executable output directory
if(NOT INSTALL_BINDIR)
  set(INSTALL_BINDIR ${CMAKE_INSTALL_BINDIR})
endif()