# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
option(TCC "Enable TCC demo" OFF)

if(TCC)
  find_library(
    ITT_LIBRARIES
    NAMES ittnotify
    HINTS ${ROOTDIR}/usr/lib/)

  find_library(
    TCC_LIBRARIES
    NAMES tcc
    HINTS ${ROOTDIR}/usr/lib64/)

  find_library(
    TCC_CACHE_LIBRARIES
    NAMES tcc_cache
    HINTS ${ROOTDIR}/usr/lib64/)

  find_library(
    TCC_STATIC_LIBRARIES
    NAMES tcc_static
    HINTS ${ROOTDIR}/usr/lib64/)
endif(TCC)
