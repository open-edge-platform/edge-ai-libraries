# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
option(COBALT "Enable compiling with Xenomai" OFF)

set(XENOMAI_DIR "/usr/xenomai" CACHE PATH "Root directory of Xenomai.")
set(XENO_BINDIR "${XENOMAI_DIR}/bin" CACHE PATH "Root directory of Xenomai.")

# Add Xenomai compile flags
if (COBALT)
  execute_process(COMMAND ${XENO_BINDIR}/xeno-config --skin posix --cc OUTPUT_VARIABLE XENO_CC OUTPUT_STRIP_TRAILING_WHITESPACE)
  execute_process(COMMAND ${XENO_BINDIR}/xeno-config --skin posix --cflags OUTPUT_VARIABLE XENO_CFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE)
  execute_process(COMMAND ${XENO_BINDIR}/xeno-config --skin posix --auto-init-solib --ldflags OUTPUT_VARIABLE XENO_LDFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE)
  set(CMAKE_CC "${CMAKE_CC} ${XENO_CC}")
  set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${XENO_CFLAGS}")
  set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} ${XENO_LDFLAGS}")

  message(STATUS "XENO_CC: ${XENO_CC}")
  message(STATUS "XENO_CFLAGS: ${XENO_CFLAGS}")
  message(STATUS "XENO_LDFLAGS: ${XENO_LDFLAGS}")
endif(COBALT)